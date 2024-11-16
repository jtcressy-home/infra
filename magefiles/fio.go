//go:build mage
// +build mage

package main

import (
	"context"
	"fmt"
	"os"
	"strings"
	"time"

	"io/ioutil"
	"log/slog"
	"path/filepath"

	"github.com/charmbracelet/huh"
	"github.com/charmbracelet/lipgloss"
	"github.com/charmbracelet/lipgloss/table"
	"github.com/dustin/go-humanize"
	"github.com/kastenhq/kubestr/pkg/fio"
	"github.com/kastenhq/kubestr/pkg/kubestr"
	"github.com/lainio/err2"
	"github.com/lainio/err2/try"
	"github.com/magefile/mage/mg"
	"github.com/magefile/mage/sh"
	"github.com/samber/lo"

	excelize "github.com/xuri/excelize/v2"
	corev1 "k8s.io/api/core/v1"
	storagev1 "k8s.io/api/storage/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
)

type Fio mg.Namespace

func runfio(ctx context.Context, testName, storageClass, nodeName string) (_ *fio.RunFIOResult, err error) {
	defer err2.Handle(&err, func(err error) error {
		slog.Error(err.Error())
		return err
	})

	fioRunner := &fio.FIOrunner{
		Cli: try.To1(kubestr.LoadKubeCli()),
	}

	return fioRunner.RunFio(ctx, &fio.RunFIOArgs{
		StorageClass: storageClass,
		Size:         "20Gi",
		Namespace:    "fio",
		NodeSelector: map[string]string{
			"kubernetes.io/hostname": nodeName,
		},
		FIOJobName:     fmt.Sprintf("%s-%s-%s", testName, storageClass, nodeName),
		FIOJobFilepath: fmt.Sprintf("magefiles/fio-tests/%s.fio", testName),
	})
}

// Run a single fio storage performance test using a specific storage class and node
func (Fio) Single(ctx context.Context) (err error) {
	defer err2.Handle(&err, func(err error) error {
		slog.Error(err.Error())
		return err
	})

	kcli := try.To1(kubestr.LoadKubeCli())
	fioRunner := &fio.FIOrunner{
		Cli: try.To1(kubestr.LoadKubeCli()),
	}

	var (
		fioJobFile   os.FileInfo
		storageClass *storagev1.StorageClass
		node         *corev1.Node
		// confirm      bool
	)
	// get git dir root path
	rootPath := try.To1(sh.OutCmd("git")("rev-parse", "--show-toplevel"))
	// todo: interactive prompt for test, storageclass, and node
	try.To(huh.NewForm(
		huh.NewGroup(
			huh.NewSelect[os.FileInfo]().
				Title("Fio Job").
				OptionsFunc(func() (options []huh.Option[os.FileInfo]) {
					files := try.To1(ioutil.ReadDir(filepath.Join(rootPath, "magefiles/fio-tests/")))
					for _, file := range lo.Filter(files, func(fileInfo os.FileInfo, _ int) bool {
						return strings.HasSuffix(fileInfo.Name(), ".fio")
					}) {
						if !file.IsDir() {
							options = append(options, huh.Option[os.FileInfo]{
								Key:   strings.TrimSuffix(file.Name(), ".fio"),
								Value: file,
							})
						}
					}
					return options
				}, &kcli).
				Value(&fioJobFile).WithHeight(6),
			// ), huh.NewGroup(
			huh.NewSelect[*storagev1.StorageClass]().
				Title("Storage Class").
				OptionsFunc(func() (options []huh.Option[*storagev1.StorageClass]) {
					scList := try.To1(kcli.StorageV1().StorageClasses().List(ctx, metav1.ListOptions{}))

					for _, sc := range scList.Items {
						options = append(options, huh.Option[*storagev1.StorageClass]{
							Key:   sc.ObjectMeta.Name,
							Value: &sc,
						})
					}
					return options
				}, &fioJobFile).
				Value(&storageClass).WithHeight(6),
			// ), huh.NewGroup(
			huh.NewSelect[*corev1.Node]().
				Title("Target Node").
				OptionsFunc(func() (options []huh.Option[*corev1.Node]) {
					nodeList := try.To1(kcli.CoreV1().Nodes().List(ctx, metav1.ListOptions{}))

					for _, node := range nodeList.Items {
						options = append(options, huh.Option[*corev1.Node]{
							Key:   node.ObjectMeta.Name,
							Value: &node,
						})
					}
					return options
				}, &storageClass).
				Value(&node).WithHeight(6),
		// ), huh.NewGroup(
		// 	huh.NewConfirm().
		// 		TitleFunc(func() string {
		// 			return fmt.Sprintf(
		// 				"Run %s test using %s storage class on node %s?",
		// 				strings.TrimSuffix(fioJobFile.Name(), ".fio"),
		// 				storageClass.ObjectMeta.Name,
		// 				node.ObjectMeta.Name,
		// 			)
		// 		}, &node).Value(&confirm),
		),
	).WithTheme(huh.ThemeCharm()).RunWithContext(ctx))

	// if !confirm {
	// 	slog.Warn("user aborted")
	// 	return nil
	// }

	result := try.To1(fioRunner.RunFio(ctx, &fio.RunFIOArgs{
		StorageClass: storageClass.ObjectMeta.Name,
		Size:         "20Gi",
		Namespace:    "fio",
		NodeSelector: map[string]string{
			"kubernetes.io/hostname": node.ObjectMeta.Name,
		},
		FIOJobName:     fmt.Sprintf("%s-%s-%s", strings.TrimSuffix(fioJobFile.Name(), ".fio"), storageClass.ObjectMeta.Name, node.ObjectMeta.Name),
		FIOJobFilepath: filepath.Join(rootPath, "magefiles/fio-tests", fioJobFile.Name()),
	}))

	if len(result.Result.Jobs) == 0 {
		slog.Debug("no results found", slog.Any("result", result))
		return fmt.Errorf("no results found")
	}
	t := table.New().
		Border(lipgloss.NormalBorder()).
		BorderStyle(lipgloss.NewStyle().Foreground(lipgloss.Color("99"))).
		StyleFunc(func(row, col int) lipgloss.Style {
			switch {
			case row == 0:
				return lipgloss.NewStyle().Foreground(lipgloss.Color("99")).Bold(true).Align(lipgloss.Center)
			default:
				return lipgloss.NewStyle().Foreground(lipgloss.Color("241"))
			}
		}).
		Headers("Storage Class", "Test Name", "Size", "Read IOPS", "Read Bandwidth", "Write IOPS", "Write Bandwidth", "Avg. Read Latency", "Avg. Write Latency", "Disk Util %").
		Rows([]string{
			result.StorageClass.ObjectMeta.Name,
			result.Result.Jobs[0].JobName,
			result.Size,
			fmt.Sprintf("%0.f", result.Result.Jobs[0].Read.Iops),
			fmt.Sprintf("%s/s", humanize.Bytes(uint64(result.Result.Jobs[0].Write.BWBytes))),
			fmt.Sprintf("%dµs", time.Duration(result.Result.Jobs[0].Read.LatNs.Mean*float32(time.Nanosecond)).Microseconds()),
			fmt.Sprintf("%dµs", time.Duration(result.Result.Jobs[0].Write.LatNs.Mean*float32(time.Nanosecond)).Microseconds()),
			fmt.Sprintf("%0.f", lo.If(len(result.Result.DiskUtil) > 0, result.Result.DiskUtil[len(result.Result.DiskUtil)-1].Util).Else(0)),
		})
	fmt.Println(t)
	return nil
}

// Run a predefined suite of fio storage tests for one or more storageClasses on a node and output results to an excel worksheet
func (Fio) Suite(ctx context.Context, nodeName string, storageClasses string) (err error) {
	defer err2.Handle(&err, func(err error) error {
		slog.Error(err.Error())
		return err
	})
	// todo: interactive prompt for node, with multiselect for test names and storageclasses

	var results []*fio.RunFIOResult
	for _, storageClass := range strings.Split(storageClasses, ",") {
		for _, testName := range []string{"fio-seq-read", "fio-seq-write", "fio-rand-read", "fio-rand-write"} {
			fmt.Println(fmt.Sprintf("Running %s test on %s storage class on node %s", testName, storageClass, nodeName))
			result, err := runfio(ctx, testName, storageClass, nodeName)
			if err != nil {
				fmt.Println(err.Error())
				return err
			}
			results = append(results, result)
		}
	}

	// todo: print results in a table
	// todo: interactively ask if user wants to save results to an excel file
	fileName := fmt.Sprintf("%s_%s_fio-suite-results.xlsx", nodeName, strings.ReplaceAll(storageClasses, ",", "_"))
	slog.Info("Generating excel spreadsheet with results...", slog.String("fileName", fileName))
	_ = try.To1(generateExcelSpreadsheet(results, fileName))
	slog.Info("Done!", slog.String("fileName", fileName))
	return nil
}

func generateExcelSpreadsheet(results []*fio.RunFIOResult, fileName string) (*excelize.File, error) {
	f := excelize.NewFile()

	// Create a new sheet.
	index, err := f.NewSheet("Sheet1")
	if err != nil {
		return nil, err
	}
	// Set active sheet of the workbook.
	f.SetActiveSheet(index)

	columns := []string{"Storage Class", "Test Name", "Size", "Read IOPS", "Read Bandwidth", "Write IOPS", "Write Bandwidth", "Avg. Read Latency", "Avg. Write Latency", "Disk Util %"}
	widths := []float64{35, 15, 5, 10, 15, 10, 15, 18, 18, 20}
	styles := []*excelize.Style{
		{ // Storage Class
			Alignment: &excelize.Alignment{
				Horizontal: "right",
			},
		},
		{ // Test Name
			Alignment: &excelize.Alignment{
				Horizontal: "right",
			},
		},
		{ // Size
			Alignment: &excelize.Alignment{
				Horizontal: "right",
			},
		},
		{ // Read IOPS
			Alignment: &excelize.Alignment{
				Horizontal: "right",
			},
			NumFmt: 2,
		},
		{ // Read Bandwidth
			Alignment: &excelize.Alignment{
				Horizontal: "right",
			},
		},
		{ // Write IOPS
			Alignment: &excelize.Alignment{
				Horizontal: "right",
			},
			NumFmt: 2,
		},
		{ // Write Bandwidth
			Alignment: &excelize.Alignment{
				Horizontal: "right",
			},
		},
		{ // Avg. Read Latency
			Alignment: &excelize.Alignment{
				Horizontal: "right",
			},
		},
		{ // Avg. Write Latency
			Alignment: &excelize.Alignment{
				Horizontal: "right",
			},
		},
		{ // Disk Util %
			Alignment: &excelize.Alignment{
				Horizontal: "right",
			},
			NumFmt: 10,
		},
	}
	for i, col := range columns {
		f.SetCellValue("Sheet1", fmt.Sprintf("%s%d", string(rune(65+i)), 1), col)
		f.SetColWidth("Sheet1", fmt.Sprintf("%s", string(rune(65+i))), fmt.Sprintf("%s", string(rune(65+i))), widths[i])
		style, err := f.NewStyle(styles[i])
		if err != nil {
			return nil, err
		}
		f.SetColStyle("Sheet1", fmt.Sprintf("%s", string(rune(65+i))), style)
	}

	for i, result := range results {
		row := []interface{}{
			result.StorageClass.ObjectMeta.Name,
			result.Result.Jobs[0].JobName,
			result.Size,
			result.Result.Jobs[0].Read.Iops,
			fmt.Sprintf("%s/s", humanize.Bytes(uint64(result.Result.Jobs[0].Read.BWBytes))),
			result.Result.Jobs[0].Write.Iops,
			fmt.Sprintf("%s/s", humanize.Bytes(uint64(result.Result.Jobs[0].Write.BWBytes))),
			fmt.Sprintf("%dµs", time.Duration(result.Result.Jobs[0].Read.LatNs.Mean*float32(time.Nanosecond)).Microseconds()),
			fmt.Sprintf("%dµs", time.Duration(result.Result.Jobs[0].Write.LatNs.Mean*float32(time.Nanosecond)).Microseconds()),
			result.Result.DiskUtil[len(result.Result.DiskUtil)-1].Util,
		}
		dataRow := i + 2
		for j, col := range row {
			f.SetCellValue("Sheet1", fmt.Sprintf("%s%d", string(rune(65+j)), dataRow), col)
		}
	}

	return f, f.SaveAs(fileName)
}
