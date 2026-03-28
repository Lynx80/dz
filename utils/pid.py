import os
import sys

def create_pid_file(pid_file="bot.pid"):
    if os.path.exists(pid_file):
        with open(pid_file, 'r') as f:
            try:
                pid = int(f.read().strip())
                if os.name == 'nt':
                    # Windows specific PID check if needed, but simple exists is often enough
                    pass
                else:
                    os.kill(pid, 0) # Throws if process not exists
                print(f"⚠️ Bot is already running (PID {pid}). Exit.")
                return False
            except:
                pass
    
    with open(pid_file, 'w') as f:
        f.write(str(os.getpid()))
    return True

def remove_pid_file(pid_file="bot.pid"):
    if os.path.exists(pid_file):
        os.remove(pid_file)
