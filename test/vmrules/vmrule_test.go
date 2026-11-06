package vmrules

import (
	"bytes"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
)

func TestVMRules(t *testing.T) {
	bin := mustPromtool(t)
	wd, err := os.Getwd()
	if err != nil {
		t.Fatal(err)
	}
	root, err := RepoRoot(wd)
	if err != nil {
		t.Fatal(err)
	}
	rules, err := Load(root)
	if err != nil {
		t.Fatal(err)
	}
	if len(rules) == 0 {
		t.Fatal("no VMRules found under kubernetes/deploy")
	}
	for _, rule := range rules {
		rule := rule
		rel, err := filepath.Rel(root, rule.File)
		if err != nil {
			t.Fatal(err)
		}
		t.Run(rel+"/"+rule.Name, func(t *testing.T) {
			if err := checkRule(t, bin, rule); err != nil {
				t.Fatal(err)
			}
		})
	}
}

func TestLoadIgnoresNonRulesAndRejectsBrokenManifests(t *testing.T) {
	root := t.TempDir()
	deploy := filepath.Join(root, "kubernetes", "deploy", "sample")
	if err := os.MkdirAll(deploy, 0o755); err != nil {
		t.Fatal(err)
	}
	writeFile(t, filepath.Join(deploy, "not-a-rule.yaml"), "kind: ConfigMap\nmetadata:\n  name: x\n")
	writeFile(t, filepath.Join(deploy, "template.yml"), "api_key: !env API_KEY\n")
	writeFile(t, filepath.Join(deploy, "sample-rules.yaml"), `
apiVersion: operator.victoriametrics.com/v1beta1
kind: VMRule
metadata:
  name: sample
  namespace: monitoring
spec:
  groups:
    - name: sample
      rules:
        - alert: Always
          expr: vector(1)
          labels:
            severity: warning
`)
	writeFile(t, filepath.Join(deploy, "sample-rules_test.yaml"), `
evaluation_interval: 1m
tests:
  - interval: 1m
    alert_rule_test:
      - eval_time: 1m
        alertname: Always
        exp_alerts:
          - exp_labels:
              severity: warning
`)
	rules, err := Load(root)
	if err != nil {
		t.Fatal(err)
	}
	if len(rules) != 1 || rules[0].Name != "sample" || rules[0].Fixture == "" {
		t.Fatalf("rules = %+v", rules)
	}
	bin := mustPromtool(t)
	if err := checkRule(t, bin, rules[0]); err != nil {
		t.Fatal(err)
	}

	writeFile(t, filepath.Join(deploy, "sample-rules_test.yml"), "tests: []\n")
	if _, err := Load(root); err == nil {
		t.Fatal("two sibling fixtures should be rejected")
	}
	if err := os.Remove(filepath.Join(deploy, "sample-rules_test.yml")); err != nil {
		t.Fatal(err)
	}

	writeFile(t, filepath.Join(deploy, "bad-rules.yaml"), "kind: VMRule\n: [\n")
	if _, err := Load(root); err == nil {
		t.Fatal("unparseable VMRule should fail")
	}
}

func TestPrepareFixtureRejectsRuleFilesAndEmptyTests(t *testing.T) {
	if _, err := PrepareFixture([]byte("rule_files:\n  - other.yml\ntests:\n  - name: x\n"), "rules.yml"); err == nil {
		t.Fatal("rule_files should be rejected")
	}
	if _, err := PrepareFixture([]byte("evaluation_interval: 1m\ntests: []\n"), "rules.yml"); err == nil {
		t.Fatal("empty tests should be rejected")
	}
	got, err := PrepareFixture([]byte("# note\nevaluation_interval: 1m\ntests:\n  - name: one\n"), "rules.yml")
	if err != nil {
		t.Fatal(err)
	}
	if !bytes.Contains(got, []byte("rule_files:\n  - rules.yml\n")) || !bytes.Contains(got, []byte("name: one")) {
		t.Fatalf("prepared fixture:\n%s", got)
	}
}

func TestPromtoolRejectsInvalidExpr(t *testing.T) {
	bin := mustPromtool(t)
	rule := Rule{
		File:      "invalid.yaml",
		Name:      "invalid",
		Namespace: "monitoring",
		GroupsYAML: []byte(`
groups:
  - name: bad
    rules:
      - alert: Bad
        expr: "((("
`),
	}
	if err := checkRule(t, bin, rule); err == nil {
		t.Fatal("invalid PromQL should fail promtool check rules")
	}
}

func checkRule(t *testing.T, bin string, rule Rule) error {
	t.Helper()
	dir := t.TempDir()
	rulesPath := filepath.Join(dir, "rules.yml")
	if err := os.WriteFile(rulesPath, rule.GroupsYAML, 0o644); err != nil {
		return err
	}
	if out, err := run(bin, dir, "check", "rules", rulesPath); err != nil {
		return fmt.Errorf("promtool check rules %s/%s: %w\n%s", rule.Namespace, rule.Name, err, out)
	}
	if rule.Fixture == "" {
		return nil
	}
	fixture, err := os.ReadFile(rule.Fixture)
	if err != nil {
		return err
	}
	prepared, err := PrepareFixture(fixture, "rules.yml")
	if err != nil {
		return fmt.Errorf("%s: %w", rule.Fixture, err)
	}
	testsPath := filepath.Join(dir, "tests.yml")
	if err := os.WriteFile(testsPath, prepared, 0o644); err != nil {
		return err
	}
	if out, err := run(bin, dir, "test", "rules", testsPath); err != nil {
		return fmt.Errorf("promtool test rules %s: %w\n%s", rule.Fixture, err, out)
	}
	return nil
}

func mustPromtool(t *testing.T) string {
	t.Helper()
	bin := os.Getenv("PROMTOOL")
	if bin == "" {
		var err error
		bin, err = exec.LookPath("promtool")
		if err != nil {
			t.Fatalf("promtool not on PATH and PROMTOOL is unset (want v%s)", promtoolVersion)
		}
	}
	out, err := exec.Command(bin, "--version").CombinedOutput()
	if err != nil {
		t.Fatalf("%s --version: %v\n%s", bin, err, out)
	}
	needle := "promtool, version " + promtoolVersion + " "
	if !strings.Contains(string(out), needle) {
		t.Fatalf("promtool must be v%s\n%s", promtoolVersion, out)
	}
	return bin
}

func run(bin, dir string, args ...string) ([]byte, error) {
	cmd := exec.Command(bin, args...)
	cmd.Dir = dir
	return cmd.CombinedOutput()
}

func writeFile(t *testing.T, path, body string) {
	t.Helper()
	if err := os.WriteFile(path, []byte(strings.TrimSpace(body)+"\n"), 0o644); err != nil {
		t.Fatal(err)
	}
}
