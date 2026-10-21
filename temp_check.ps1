$items = Get-ChildItem -Path $env:TEMP -Force -ErrorAction SilentlyContinue
$total = ($items | Measure-Object -Property Length -Sum).Sum
Write-Host ("Temp files: " + $items.Count + " | Total: " + [math]::Round($total/1MB, 2) + " MB")