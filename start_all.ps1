# Kick off Rasa core, Rasa actions, LINE bridge (node), and Cloudflare Tunnel in separate PowerShell windows.
# Adjust tunnel name/token and paths as needed.

$Root = "C:\Users\asus\.Ld2VirtualBox\Desktop\my_rasa_bot"
$NodeDir = "$Root\rasa-line-bot"
$TunnelName = "<YOUR_TUNNEL_NAME>"  # replace with your Cloudflare tunnel name or use token command

function Start-App {
    param(
        [string]$Title,
        [string]$WorkDir,
        [string]$Command
    )
    Start-Process powershell.exe -ArgumentList @(
        "-NoExit",
        "-Command",
        "cd '$WorkDir'; $Command"
    ) -WindowStyle Normal -Wait:$false -WorkingDirectory $WorkDir
}

# Rasa core server
Start-App -Title "rasa-core" -WorkDir $Root -Command "rasa run --enable-api --cors '*' --port 5005 --debug"

# Rasa action server
Start-App -Title "rasa-actions" -WorkDir $Root -Command "rasa run actions --port 5055 --debug"

# LINE bridge (Node)
Start-App -Title "line-bridge" -WorkDir $NodeDir -Command "node app.js"

# Cloudflare tunnel (optional) - uncomment and set the name/token
# Start-App -Title "cloudflared" -WorkDir $Root -Command "cloudflared tunnel run $TunnelName"
