param(
    [switch]$Full
)

$ErrorActionPreference = "Stop"

if (Get-Command uv -ErrorAction SilentlyContinue) {
    uv tool install --force "git+https://github.com/BehnamJalaliCo/CodeCortex.git"
} elseif (Get-Command pipx -ErrorAction SilentlyContinue) {
    pipx install --force "git+https://github.com/BehnamJalaliCo/CodeCortex.git"
} else {
    py -m pip install --user --upgrade "git+https://github.com/BehnamJalaliCo/CodeCortex.git"
}

if ($Full) {
    cortex backend install all
}

Write-Host "CodeCortex installed. Run: cortex bootstrap"
