// Package vmrules checks every VMRule manifest under kubernetes/deploy.
package vmrules

import (
	"bufio"
	"bytes"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"

	"gopkg.in/yaml.v3"
)

const promtoolVersion = "3.5.0"

// Rule is one VMRule document extracted from a manifest.
type Rule struct {
	File      string
	Name      string
	Namespace string
	// GroupsYAML is a promtool rules file containing this rule's groups.
	GroupsYAML []byte
	// Fixture is the sibling promtool unit-test file, or empty when the rule
	// is syntax-checked only.
	Fixture string
}

// RepoRoot walks up from dir until it finds kubernetes/deploy.
func RepoRoot(dir string) (string, error) {
	for {
		info, err := os.Stat(filepath.Join(dir, "kubernetes", "deploy"))
		if err == nil && info.IsDir() {
			return dir, nil
		}
		parent := filepath.Dir(dir)
		if parent == dir {
			return "", fmt.Errorf("kubernetes/deploy not found from %s", dir)
		}
		dir = parent
	}
}

// Load walks kubernetes/deploy under repoRoot and returns every VMRule.
func Load(repoRoot string) ([]Rule, error) {
	deploy := filepath.Join(repoRoot, "kubernetes", "deploy")
	var rules []Rule
	err := filepath.WalkDir(deploy, func(path string, d os.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if d.IsDir() {
			return nil
		}
		ext := strings.ToLower(filepath.Ext(path))
		if ext != ".yaml" && ext != ".yml" {
			return nil
		}
		data, err := os.ReadFile(path)
		if err != nil {
			return err
		}
		if !fileHasVMRule(data) {
			return nil
		}
		found, err := parseVMRules(path, data)
		if err != nil {
			return err
		}
		if len(found) == 0 {
			return fmt.Errorf("%s: matched kind: VMRule but no VMRule documents were parsed", path)
		}
		fixture, err := siblingFixture(path)
		if err != nil {
			return err
		}
		if fixture != "" && len(found) != 1 {
			return fmt.Errorf("%s: a fixture requires exactly one VMRule document, found %d", path, len(found))
		}
		for i := range found {
			found[i].Fixture = fixture
		}
		rules = append(rules, found...)
		return nil
	})
	return rules, err
}

func fileHasVMRule(data []byte) bool {
	sc := bufio.NewScanner(bytes.NewReader(data))
	// Manifest lines are short. A long line is not a kind field.
	sc.Buffer(make([]byte, 0, 64*1024), 1024*1024)
	for sc.Scan() {
		if isVMRuleKindLine(sc.Text()) {
			return true
		}
	}
	if sc.Err() != nil {
		return bytes.Contains(data, []byte("kind: VMRule"))
	}
	return false
}

func isVMRuleKindLine(line string) bool {
	line = strings.TrimSpace(line)
	if line == "" || strings.HasPrefix(line, "#") {
		return false
	}
	if hash := strings.IndexByte(line, '#'); hash >= 0 {
		line = strings.TrimSpace(line[:hash])
	}
	return line == "kind: VMRule" || line == `kind: "VMRule"` || line == "kind: 'VMRule'"
}

func parseVMRules(path string, data []byte) ([]Rule, error) {
	dec := yaml.NewDecoder(bytes.NewReader(data))
	var rules []Rule
	docNum := 0
	for {
		var doc yaml.Node
		err := dec.Decode(&doc)
		if err == io.EOF {
			break
		}
		docNum++
		if err != nil {
			return nil, fmt.Errorf("%s: document %d: %w", path, docNum, err)
		}
		root := documentRoot(&doc)
		if root == nil || root.Kind != yaml.MappingNode {
			continue
		}
		if scalar(mapGet(root, "kind")) != "VMRule" {
			continue
		}
		api := scalar(mapGet(root, "apiVersion"))
		if !strings.Contains(api, "operator.victoriametrics.com/") {
			return nil, fmt.Errorf("%s: document %d: VMRule apiVersion %q is not operator.victoriametrics.com", path, docNum, api)
		}
		meta := mapGet(root, "metadata")
		name := scalar(mapGet(meta, "name"))
		namespace := scalar(mapGet(meta, "namespace"))
		if name == "" || namespace == "" {
			return nil, fmt.Errorf("%s: document %d: VMRule needs metadata.name and metadata.namespace", path, docNum)
		}
		groups := mapGet(mapGet(root, "spec"), "groups")
		if groups == nil || groups.Kind != yaml.SequenceNode || len(groups.Content) == 0 {
			return nil, fmt.Errorf("%s: VMRule %s/%s has no rule groups", path, namespace, name)
		}
		encoded, err := encodeGroups(groups)
		if err != nil {
			return nil, fmt.Errorf("%s: VMRule %s/%s: %w", path, namespace, name, err)
		}
		rules = append(rules, Rule{
			File:       path,
			Name:       name,
			Namespace:  namespace,
			GroupsYAML: encoded,
		})
	}
	return rules, nil
}

func documentRoot(doc *yaml.Node) *yaml.Node {
	if doc == nil {
		return nil
	}
	if doc.Kind == yaml.DocumentNode {
		if len(doc.Content) != 1 {
			return nil
		}
		return doc.Content[0]
	}
	return doc
}

func mapGet(n *yaml.Node, key string) *yaml.Node {
	if n == nil || n.Kind != yaml.MappingNode {
		return nil
	}
	for i := 0; i+1 < len(n.Content); i += 2 {
		if n.Content[i].Value == key {
			return n.Content[i+1]
		}
	}
	return nil
}

func scalar(n *yaml.Node) string {
	if n == nil || n.Kind != yaml.ScalarNode {
		return ""
	}
	return n.Value
}

func encodeGroups(groups *yaml.Node) ([]byte, error) {
	doc := &yaml.Node{
		Kind: yaml.DocumentNode,
		Content: []*yaml.Node{{
			Kind: yaml.MappingNode,
			Tag:  "!!map",
			Content: []*yaml.Node{
				{Kind: yaml.ScalarNode, Tag: "!!str", Value: "groups"},
				groups,
			},
		}},
	}
	var buf bytes.Buffer
	enc := yaml.NewEncoder(&buf)
	enc.SetIndent(2)
	if err := enc.Encode(doc); err != nil {
		return nil, err
	}
	if err := enc.Close(); err != nil {
		return nil, err
	}
	return buf.Bytes(), nil
}

// siblingFixture returns <name>_test.yaml or <name>_test.yml next to the manifest.
func siblingFixture(rulePath string) (string, error) {
	ext := filepath.Ext(rulePath)
	base := strings.TrimSuffix(rulePath, ext)
	var found []string
	for _, candidate := range []string{base + "_test.yaml", base + "_test.yml"} {
		info, err := os.Stat(candidate)
		if err == nil && !info.IsDir() {
			found = append(found, candidate)
		} else if err != nil && !os.IsNotExist(err) {
			return "", err
		}
	}
	switch len(found) {
	case 0:
		return "", nil
	case 1:
		return found[0], nil
	default:
		return "", fmt.Errorf("%s: both %s and %s exist; keep one fixture", rulePath, found[0], found[1])
	}
}

// PrepareFixture checks a promtool unit-test file and points it at rulesName.
// The fixture must not set rule_files. The returned bytes are what promtool test rules reads.
func PrepareFixture(fixture []byte, rulesName string) ([]byte, error) {
	var doc yaml.Node
	if err := yaml.Unmarshal(fixture, &doc); err != nil {
		return nil, fmt.Errorf("fixture: %w", err)
	}
	root := documentRoot(&doc)
	if root == nil || root.Kind != yaml.MappingNode {
		return nil, fmt.Errorf("fixture must be a single YAML mapping")
	}
	if mapGet(root, "rule_files") != nil {
		return nil, fmt.Errorf("omit rule_files; the runner injects the VMRule groups as %s", rulesName)
	}
	tests := mapGet(root, "tests")
	if tests == nil || tests.Kind != yaml.SequenceNode || len(tests.Content) == 0 {
		return nil, fmt.Errorf("fixture tests must be a non-empty list")
	}
	body := bytes.TrimSpace(fixture)
	body = bytes.TrimPrefix(body, []byte("---"))
	body = bytes.TrimSpace(body)
	var out bytes.Buffer
	fmt.Fprintf(&out, "rule_files:\n  - %s\n", rulesName)
	out.Write(body)
	if !bytes.HasSuffix(body, []byte("\n")) {
		out.WriteByte('\n')
	}
	return out.Bytes(), nil
}
