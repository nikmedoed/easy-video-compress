import os
import sys
import locale
import winreg as reg

# Расширения видеофайлов
VIDEO_EXTS = ['.mp4', '.mkv', '.avi', '.mov', '.flv', '.wmv', '.webm']

# Локализация названия пункта
lang = locale.getdefaultlocale()[0] or ''
if lang.startswith('ru'):
    MENU_LABEL = 'Сжать видео (FFmpeg)'
else:
    MENU_LABEL = 'Compress video (FFmpeg)'

# Пути
SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))
BATCH_PATH = os.path.join(SCRIPT_DIR, 'compress.bat')
ICON_PATH = os.path.join(SCRIPT_DIR, 'icon', 'icon.ico')

# Базовый ключ
BASE_KEY = r'Software\Classes\AllFileSystemObjects\shell\CompressVideo'
COMMAND_KEY = BASE_KEY + r'\command'

# Функции для работы с реестром

def set_value(root, path, name, value, val_type=reg.REG_SZ):
    key = reg.CreateKey(root, path)
    reg.SetValueEx(key, name, 0, val_type, value)
    reg.CloseKey(key)


def delete_tree(root, path):
    try:
        reg.DeleteKey(root, path)
    except FileNotFoundError:
        pass
    except OSError:
        # Удаляем вложенные ключи
        key = reg.OpenKey(root, path, 0, reg.KEY_READ)
        try:
            i = 0
            while True:
                sub = reg.EnumKey(key, i)
                delete_tree(root, path + '\\' + sub)
                i += 1
        except OSError:
            pass
        finally:
            reg.CloseKey(key)
        try:
            reg.DeleteKey(root, path)
        except Exception:
            pass


def main():
    # 1) Удаляем старые ключи
    delete_tree(reg.HKEY_CURRENT_USER, BASE_KEY)
    # Удаляем отдельные для расширений и папок
    for ext in VIDEO_EXTS:
        delete_tree(reg.HKEY_CURRENT_USER, f'Software\\Classes\\SystemFileAssociations\\{ext}\\shell\\CompressVideo')
    delete_tree(reg.HKEY_CURRENT_USER, r'Software\Classes\Directory\shell\CompressVideo')

    # 2) Создаем основной ключ и свойства
    set_value(reg.HKEY_CURRENT_USER, BASE_KEY, None, MENU_LABEL)
    if os.path.isfile(ICON_PATH):
        set_value(reg.HKEY_CURRENT_USER, BASE_KEY, 'Icon', ICON_PATH)

    # AppliesTo — только папки и видеофайлы
    applies = ['System.ItemType:=Directory'] + [f'System.FileExtension:={e}' for e in VIDEO_EXTS]
    set_value(reg.HKEY_CURRENT_USER, BASE_KEY, 'AppliesTo', ' OR '.join(applies))

    # Один процесс для всех выделенных объектов
    set_value(reg.HKEY_CURRENT_USER, BASE_KEY, 'MultiSelectModel', 'Player')

    # Команда запуска
    cmd = f'cmd.exe /k "{BATCH_PATH}" %V'
    set_value(reg.HKEY_CURRENT_USER, COMMAND_KEY, None, cmd)

    print('✅ Контекстное меню установлено: ' + MENU_LABEL)
    print('Перезапустите Проводник или выйдите/войдите в систему, чтобы изменения вступили в силу.')


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print('❌ Ошибка при установке:', e)
        sys.exit(1)
