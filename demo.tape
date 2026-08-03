Output assets/demo.gif

Set Shell "bash"
Set FontSize 14
Set Width 680
Set Height 360
Set Theme "Catppuccin Mocha"
Set Padding 16
Set TypingSpeed 70ms
Set PlaybackSpeed 0.85

# Warm up, set env, clear before Show
Hide
Type "export TD_DB_PATH=/tmp/td_demo.db && rm -f $TD_DB_PATH && td --version > /dev/null 2>&1 && clear"
Enter
Sleep 3s
Show

# Launch the TUI — env var already set in Hide
Type "td -l work"
Enter
Sleep 1400ms

# Add three tasks
Type "a"
Sleep 300ms
Type "design API endpoints"
Enter
Sleep 400ms

Type "a"
Sleep 300ms
Type "write unit tests"
Enter
Sleep 400ms

Type "a"
Sleep 300ms
Type "deploy to staging"
Enter
Sleep 600ms

# Star the top task
Up
Up
Type "s"
Sleep 600ms

# Toggle middle task done
Down
Type " "
Sleep 1200ms

# Quit
Type "q"
Sleep 300ms
