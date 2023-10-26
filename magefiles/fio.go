//go:build mage
// +build mage

package main

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"
	"time"

	"github.com/dustin/go-humanize"
	"github.com/magefile/mage/mg"

	"github.com/kastenhq/kubestr/pkg/fio"
	"github.com/kastenhq/kubestr/pkg/kubestr"

	excelize "github.com/xuri/excelize/v2"
)

type Fio mg.Namespace

func runfio(ctx context.Context, testName, storageClass, nodeName string) (*fio.RunFIOResult, error) {
	cli, err := kubestr.LoadKubeCli()
	if err != nil {
		fmt.Println(err.Error())
		return nil, err
	}
	fioRunner := &fio.FIOrunner{
		Cli: cli,
	}

	return fioRunner.RunFio(ctx, &fio.RunFIOArgs{
		StorageClass: storageClass,
		Size:         "20Gi",
		Namespace:    "default",
		NodeSelector: map[string]string{
			"kubernetes.io/hostname": nodeName,
		},
		FIOJobName:     fmt.Sprintf("%s-%s-%s", testName, storageClass, nodeName),
		FIOJobFilepath: fmt.Sprintf("magefiles/fio-tests/%s.fio", testName),
	})
}

// Run a single fio storage performance test using a specific storage class and node
func (Fio) Single(ctx context.Context, testName, storageClass, nodeName string) error {
	result, err := runfio(ctx, testName, storageClass, nodeName)
	if err != nil {
		fmt.Println(err.Error())
		return err
	}
	fioResultJson, err := json.Marshal(result)
	if err != nil {
		fmt.Println(err.Error())
		return err
	}
	fmt.Println(string(fioResultJson))
	return nil
}

// Run a predefined suite of fio storage tests for one or more storageClasses on a node and output results to an excel worksheet
func (Fio) Suite(ctx context.Context, nodeName string, storageClasses string) error {
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
	fileName := fmt.Sprintf("%s-fio-suite-results.xlsx", nodeName)
	fmt.Println(fmt.Sprintf("Generating excel spreadsheet with results... (%s)", fileName))
	_, err := generateExcelSpreadsheet(results, fileName)
	if err != nil {
		fmt.Println(err.Error())
		return err
	}
	fmt.Println("Done!")
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
