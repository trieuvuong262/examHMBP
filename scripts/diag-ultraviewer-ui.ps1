Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$ae = [System.Windows.Automation.AutomationElement]
$proc = Get-Process UltraViewer_Desktop -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $proc) { Write-Output 'NO PROCESS'; exit 1 }
$cond = New-Object System.Windows.Automation.PropertyCondition($ae::ProcessIdProperty, $proc.Id)
$win = $ae::RootElement.FindFirst([System.Windows.Automation.TreeScope]::Children, $cond)
if (-not $win) { Write-Output 'NO WINDOW'; exit 1 }
$ed = New-Object System.Windows.Automation.PropertyCondition(
    $ae::ControlTypeProperty, [System.Windows.Automation.ControlType]::Edit)
$all = $win.FindAll([System.Windows.Automation.TreeScope]::Descendants, $ed)
Write-Output "COUNT: $($all.Count)"
for ($i = 0; $i -lt $all.Count; $i++) {
    $el = $all[$i]
    $val = ''
    try {
        $vp = $el.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
        if ($vp) { $val = $vp.Current.Value }
    } catch {}
    Write-Output "$i val=[$val] name=[$($el.Current.Name)] aid=[$($el.Current.AutomationId)]"
}
