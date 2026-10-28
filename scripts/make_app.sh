#!/bin/zsh
# Builds ~/Applications/Friday.app (Spotlight, Dock, Launchpad). Re-run it if you move the project folder.
DIR="${0:A:h:h}"
chmod +x "$DIR/scripts/wake.sh"
osacompile -o "$HOME/Applications/Friday.app" -e "do shell script quoted form of \"$DIR/scripts/wake.sh\" & \" > /dev/null 2>&1 &\""
echo "Built $HOME/Applications/Friday.app"
