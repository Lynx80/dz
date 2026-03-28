# Workspace Maintenance for AI Efficiency

To keep the AI ("Antigravity") fast and minimize token usage, follow these simple rules:

### 1. Keep the Root Clean
- **Archive old scripts:** Move `test_*.py` and `debug_*.py` to the `archive/` folder once you are done with them.
- **Why?** The AI sees all files in your workspace. 100 files = 100x more "noise" for the AI to process.

### 2. Manage Open Tabs
- Close files in your editor that you aren't currently working on.
- **Why?** The content of all open tabs is sent to the AI with every message.

### 3. Clear Logs Regularly
- If `bot_log.txt` or `bot.log` becomes huge, clear them:
  ```powershell
  Clear-Content bot.log
  ```
- **Why?** Huge text files eat up the "context window" (tokens).

### 4. Restart the Chat
- If a conversation becomes very long (many messages), start a new one for new tasks.
- **Why?** Long history = higher token cost per message.

### 5. Use the `.gitignore`
- I've configured `.gitignore` to ignore logs and databases. This helps me focus only on your code.
