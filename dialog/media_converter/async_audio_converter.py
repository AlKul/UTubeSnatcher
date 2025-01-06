import asyncio
from pydub import AudioSegment
import functools

import os


async def async_convert_audio(file_path, target_format, max_size=50 * 1_000_000):
    loop = asyncio.get_event_loop()
    try:
        # Проверяем, существует ли файл
        if not os.path.exists(file_path):
            print(f"Файл {file_path} не найден.")
            return

        # Получаем имя файла без расширения
        base_name = os.path.splitext(file_path)[0]
        # Формируем новое имя с нужным расширением
        output_file = f"{base_name}.{target_format}"

        # # Асинхронно загружаем и конвертируем файл
        # audio = await loop.run_in_executor(None, AudioSegment.from_file, input_file)

        # Выполняем синхронный вызов в отдельном потоке
        def sync_convert():
            audio = AudioSegment.from_file(file_path)
            filesize = os.path.getsize(file_path)
            if filesize > max_size:
                print("Аудио большое, попробуем сжать")
                audio.export('./results/check1.mp3', format=target_format, parameters=["-ac", "1", "-b:a", "64k"])
            else:
                audio.export(output_file, format=target_format)
            


        # await loop.run_in_executor(None, functools.partial(audio.export, output_file, format=target_format))
        await loop.run_in_executor(None, sync_convert)

        print(f"Файл успешно конвертирован: {output_file}")

        return output_file
    except Exception as e:
        print(f"Ошибка при конвертации: {e}")


# Использование
async def main():
    input_path = "./results/Blues_A.m4a"  # Замените на ваш файл
    target_format = "mp3"  # Укажите формат, например "mp3"
    await async_convert_audio(input_path, target_format)

# Запуск асинхронной функции
asyncio.run(main())