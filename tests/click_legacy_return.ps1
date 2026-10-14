param([Parameter(Mandatory=$true)][int]$LegacyProcessId)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$condition = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ProcessIdProperty, $LegacyProcessId)
$window = [System.Windows.Automation.AutomationElement]::RootElement.FindFirst([System.Windows.Automation.TreeScope]::Children, $condition)
if (!$window) { throw 'Visible WPF legacy window not found.' }
$buttonCondition = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::AutomationIdProperty, 'ModeSwitchButton')
$button = $window.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $buttonCondition)
if (!$button -or !$button.Current.IsEnabled) { throw 'WPF return button not available.' }
$pattern = $button.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
$pattern.Invoke()
