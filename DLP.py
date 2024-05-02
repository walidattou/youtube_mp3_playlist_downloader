from customtkinter import *
from pytube import YouTube
from pytube import Playlist
from customtkinter import filedialog
from PIL import ImageTk, Image
import os

root = CTk()
root.geometry('500x300')
root.title("Youtube downloader")
root.minsize(500, 300)
root.maxsize(500, 300)


fileB = ""  # Variable to store the chosen directory

def Start_press():
    global fileB  # Use the global variable

    try:
        PlayL = YouTube(EntryV.get(), use_oauth=True, allow_oauth_cache=True)
        PlayL.streams.filter(only_audio=True).first().download(output_path=fileB)

        for filename in os.listdir(fileB):
            if not filename.endswith('.mp3'):
                m = filename.replace('.mp4', '')
                new_name = m + '.mp3'
                os.rename(rf'{fileB}/{filename}', rf'{fileB}/{new_name}')

    except:
        PlayL = Playlist(EntryV.get())
        for link in PlayL:

            try:
                video = YouTube(link)
                video.streams.filter(only_audio=True).first().download(output_path=fileB)

                for filename in os.listdir(fileB):
                    if not filename.endswith('.mp3'):
                        m = filename.replace('.mp4', '')
                        new_name = m + '.mp3'
                        os.rename(rf'{fileB}/{filename}', rf'{fileB}/{new_name}')

            except:
                pass

def browse_directory():
    global fileB
    fileB = filedialog.askdirectory()

EntryV = CTkEntry(master=root, width=300, placeholder_text='Video or playlist link in here')
EntryV.place(x=100, y=110)

brows = CTkButton(master=root, corner_radius=0, text='Folder location', command=browse_directory)
brows.place(x=250, y=200)

Startb = CTkButton(master=root, corner_radius=0, text='Start', command=Start_press)
Startb.place(x=100, y=200)

root.title("youtube Audio downloader")
root.mainloop()