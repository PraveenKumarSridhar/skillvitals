# VHS tape for the skillvitals demo GIF.
# Render:  vhs scripts/demo.tape   (run scripts/gen_demo_home.py /tmp/demo-claude first)
# Uses synthetic data in /tmp/demo-claude — never real ~/.claude.

Output docs/skillvitals-demo.gif

Set Shell zsh
Set FontSize 16
Set Width 1180
Set Height 860
Set Padding 24
Set Margin 0
Set TypingSpeed 60ms
Set PlaybackSpeed 1.0

# --- setup (not recorded): point at the synthetic demo home ---
Hide
Type "export PATH=$HOME/.local/bin:$PATH SKILLVITALS_CLAUDE_HOME=/tmp/demo-claude SKILLVITALS_HOME=/tmp/demo-sv"
Enter
Type "clear"
Enter
Show

# --- beat 1: the headline scan ---
Sleep 600ms
Type "skillvitals scan"
Sleep 500ms
Enter
Sleep 5s

# --- beat 2: what to do about it ---
Type "clear"
Enter
Sleep 300ms
Type "skillvitals prescribe"
Sleep 500ms
Enter
Sleep 4500ms
