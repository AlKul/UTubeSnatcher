from pydub import AudioSegment

def convert_m4a_to_mp3(input_file, output_file):
    try:
        # Загружаем m4a-файл
        audio = AudioSegment.from_file(input_file, format="m4a")
        # Конвертируем в mp3
        audio.export(output_file, format="mp3")
        print(f"Файл успешно конвертирован: {output_file}")
    except Exception as e:
        print(f"Ошибка при конвертации: {e}")

from pydub import AudioSegment
import os


def convert_audio(input_file, target_format):
    try:
        # Проверяем, существует ли файл
        if not os.path.exists(input_file):
            print(f"Файл {input_file} не найден.")
            return
        
        # Получаем имя файла без расширения
        base_name = os.path.splitext(input_file)[0]
        # Формируем новое имя с нужным расширением
        output_file = f"{base_name}.{target_format}"
        
        # Загружаем исходный файл
        audio = AudioSegment.from_file(input_file)
        # Конвертируем в нужный формат
        audio.export(output_file, format=target_format)
        print(f"Файл успешно конвертирован: {output_file}")
    except Exception as e:
        print(f"Ошибка при конвертации: {e}")

# Использование
input_path = "./results/Groovy Guitar Backing Track (Blues A Minor).m4a"  # Замените на ваш файл
target_format = "mp3"         # Укажите формат, например "mp3"
convert_audio(input_path, target_format)
# "results/Groovy Guitar Backing Track (Blues A Minor).m4a"


# # Использование
# input_path = "./../results/Groovy Guitar Backing Track (Blues A Minor).m4a"  # Замените на ваш файл
# output_path = "your_file.mp3"  # Название выходного файла
# convert_m4a_to_mp3(input_path, output_path)
