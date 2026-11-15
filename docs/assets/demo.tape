# Record the README demo GIF with charmbracelet/vhs:
#   vhs docs/assets/demo.tape
# Runs against a throwaway HOME so nothing real is written.

Output docs/assets/demo.gif

Set Shell "bash"
Set FontSize 18
Set Width 1100
Set Height 620
Set Padding 24
Set Theme "Catppuccin Mocha"
Set TypingSpeed 45ms

Hide
Type "export DEMO_HOME=$(mktemp -d) && mkdir -p $DEMO_HOME/.claude && clear"
Enter
Show

Type "vibe kits list"
Sleep 400ms
Enter
Sleep 2s

Type "vibe kits claude-code install --dry-run --home $DEMO_HOME"
Sleep 400ms
Enter
Sleep 4s

Type "vibe kits guardrails install --dry-run --yes --home $DEMO_HOME"
Sleep 400ms
Enter
Sleep 4s

Hide
Type "rm -rf $DEMO_HOME"
Enter
