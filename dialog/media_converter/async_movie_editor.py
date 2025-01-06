import asyncio
import os 
from moviepy.editor import VideoFileClip

async def video_size_reducer_async(filepath, max_size):
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

    loop = asyncio.get_event_loop()

    def video_size_reducer():
        filesize = os.path.getsize(filepath)
        video = VideoFileClip(filepath)
        if filesize > max_size:
            resize_coeff = max_size / filesize
            video_resized = video.resize(resize_coeff)
            video_resized.write_videofile(filepath)
            print("Video resized")
    
    await loop.run_in_executor(None, video_size_reducer)
