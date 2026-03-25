import subprocess
import time
import sys

# Попытка передать пароль через stdin для ssh на Windows
# (Обычно OpenSSH блокирует это, но мы попробуем)

password = "BotSecurePass123!"
command = "sudo /usr/local/bin/manage_docker_dz.sh restart"
host = "bot_admin@185.209.28.253"

# Для Windows иногда работает вариант с тильдой или специальным перенаправлением
# Но проще всего запустить процесс и ждать промпта
# Однако в неинтерактивном режиме это сложно.

print(f"Попытка выполнить: {command} на {host}")

# Самый простой способ - предложить пользователю команду, если автомат не сработает.
sys.exit(0)
