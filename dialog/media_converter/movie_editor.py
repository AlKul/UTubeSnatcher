import os 
from moviepy.editor import VideoFileClip

filesize = os.path.getsize("/Users/alexx/Documents/Coding/Python_today/Youtube downloader/results/Купер_обнаружил_секретную_базу_Наса_Интерстеллар.mp4")

video = VideoFileClip("/Users/alexx/Documents/Coding/Python_today/Youtube downloader/results/Купер_обнаружил_секретную_базу_Наса_Интерстеллар.mp4")
video_resized = video.resize(0.5)

def video_size_reducer(filepath, max_size):
    """
    # Check if the file size is greater than the maximum allowed size
    if filesize > max_size:
        # Calculate the resize coefficient
        resize_coeff = (max_size / filesize) ** 0.5
        # Resize the video
        video_resized = VideoFileClip(filepath).resize(resize_coeff)
        # Write the resized video back to the file
        video_resized.write_videofile(filepath, codec='libx264')
        print("Video resized")
    else:
        print("Video size is within the limit")
    """
    filesize = os.path.getsize(filepath)
    if filesize > max_size:
        resize_coeff = max_size / filesize
        video_resized = video.resize(resize_coeff)
        video_resized.write_videofile(filepath)
        print("Video resized")

video_size_reducer("/Users/alexx/Documents/Coding/Python_today/Youtube downloader/results/Пастуховские четверги. Владимир Пастухов и Алексей Венедиктов / 12.09.24.mp4", 50*1_000_000)

print("Длительность:", video.duration, "секунд")
print("Разрешение:", video.size)
print("Частота кадров:", video.fps, "кадров в секунду")