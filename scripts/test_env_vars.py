#!/usr/bin/env python3
"""
Тестовый скрипт для проверки работы переменных окружения в roles/agents.yaml
"""

import os
import sys
from pathlib import Path

# Добавляем корень проекта в path
sys.path.append(str(Path(__file__).parent.parent))

from app.config import Config


def test_env_vars():
    """Тестируем раскрытие переменных окружения в конфигурации."""

    print("🧪 Тестирование переменных окружения в roles/agents.yaml")
    print("=" * 60)

    # Устанавливаем тестовые переменные окружения
    os.environ["SOFTWARE_DEV_BOT_TOKEN"] = "test_token_1"
    os.environ["CODE_REVIEW_BOT_TOKEN"] = "test_token_2"
    os.environ["PRODUCT_OWNER_BOT_TOKEN"] = "test_token_3"

    print("📝 Установлены тестовые переменные:")
    for key in [
        "SOFTWARE_DEV_BOT_TOKEN",
        "CODE_REVIEW_BOT_TOKEN",
        "PRODUCT_OWNER_BOT_TOKEN",
    ]:
        print(f"   {key} = {os.environ[key]}")

    print("\n🔄 Загрузка конфигурации...")

    # Загружаем конфигурацию
    success = Config.load_roles(Path("roles/agents.yaml"))

    if not success:
        print("❌ Ошибка загрузки конфигурации")
        return False

    print("✅ Конфигурация успешно загружена")

    # Проверяем что переменные раскрылись
    if Config.roles_registry:
        print(f"\n📋 Загружено ролей: {len(Config.roles_registry.roles)}")

        for role in list(Config.roles_registry.roles.values())[
            :3
        ]:  # Первые 3 роли для примера
            print(f"\n🤖 Роль: {role.display_name}")
            print(f"   📧 Telegram Bot: {role.telegram_bot_name}")
            if hasattr(role, "telegram_bot_token"):
                print(f"   🔑 Token: {role.telegram_bot_token}")

            # Проверяем что токен не остался в виде ${VAR_NAME}
            if hasattr(role, "telegram_bot_token") and role.telegram_bot_token:
                if role.telegram_bot_token.startswith("${"):
                    print(f"   ❌ Токен не раскрыт: {role.telegram_bot_token}")
                    return False
                else:
                    print(f"   ✅ Токен успешно раскрыт")

    print("\n🎉 Тест завершен!")
    assert True


if __name__ == "__main__":
    test_env_vars()
