
#---------------------------------------------------------------------------------------------------------------#
# Outside Requirements
# py -m pip install --upgrade package_name
#---------------------------------------------------------------------------------------------------------------#
# ffmpeg - installed and in path
# Obtained from: https://www.videohelp.com/software/ffmpeg

# Example:
# python VIPs_Normalize_Media.py

#---------------------------------------------------------------------------------------------------------------#
# Processing Flow
# 1. Load configuration values from config.toml
# 2. Load and validate the configured directories
# 3. Recursively scan each directory for files newer than the configured age limit
# 4. Categorize each file as a deletion, image, movie, or unsupported file
# 5. Process deletions, images, and movies using separate thread pools
# 6. Preserve metadata and timestamps while converting or resizing supported media
# 7. Display totals and file-size results
#---------------------------------------------------------------------------------------------------------------#



#---------------------------------------------------------------------------------------------------------------#
# Load Modules
# py -m pip install --upgrade
#---------------------------------------------------------------------------------------------------------------#
import os                                                        # interact with the file system
from datetime import datetime                                    # work with dates and times
from rich import print
import glob                                                      # handling wildcard searches, ex:  *.jpg
from concurrent.futures import ThreadPoolExecutor                # used for multi threading
import subprocess                                                # used for running external commands
import json
import unicodedata                                               # unicode characters
import re                                                        # work with regex
import uuid                                                      # unique values
from send2trash import send2trash                                # Use the recycle bin (windows)
import tomllib                                                   # Uses a property/config file

from hachoir.parser import createParser                          # hachoir is used to handle movie metadata 
from hachoir.metadata import extractMetadata                     # working with movie metadata
from wand.image import Image as WandImage                        # ability to work with heic files  ( renamed to avoid naming conflict )
from time import sleep                                           # ability to introduce time delays
import tempfile                                                  # ability to create temporary files/directories per thread
import shutil                                                    # Copy files
from PIL import Image as PILImage                                # Ability to resize images ( renamed to avoid naming conflict )

from Utilities.Rich_Progress import Rich_Progress                # Used for displaying progress bars and other rich text in the console

#---------------------------------------------------------------------------------------------------------------#
# Normalize, convert, resize, rename, and preserve metadata for image and video files
#---------------------------------------------------------------------------------------------------------------#
class Fix_Files():

    #---------------------------------------------------------------------------------------------------------------#
    # Initialize the class
    #---------------------------------------------------------------------------------------------------------------#
    def __init__( self ):
        self.Progress = Rich_Progress()
        self.Console = self.Progress.Console

        self.Today = datetime.today()

        self.Size_Before = 0
        self.Size_After  = 0

        self.Media = {
            "Directories": [],
            "Files":       [],
            "Deletes":     [],
            "Images":      [],
            "Movies":      [],
            "Others":      []
        }

        self.Tasks = {
            "Deletes": None,
            "Movies":  None,
            "Images":  None,
            "Others":  None
        }


        self.Config = self.Load_Config( os.path.join( os.path.dirname( os.path.abspath( __file__ ) ), "config.toml" ) )

        self.ExifTool = self.Config["Executables"]["Exiftool"]
        self.FFMpeg = self.Config["Executables"]["FFMpeg"]

        self.Age_Convert    = self.Config["Processing"]["Age_Convert"]
        self.Width_Limit    = self.Config["Processing"]["Width_Limit"]
        self.Height_Limit   = self.Config["Processing"]["Height_Limit"]
        self.FILENAME_LIMIT = self.Config["Processing"]["Filename_Limit"]

        self.Threads        = self.Config["Threads"]
        self.Data_Types     = self.Config["File_Types"]

        # In the event that a thread errors, it will set this flag.  Other threads will not be run
        self.Stop_Due_to_Error = False

        self.Console.print( f"[cyan]__________________________________________________________________________________[/cyan]" )
        self.Console.print( f"[cyan] Media Conversions[/cyan]" )
        self.Console.print( f"[cyan]__________________________________________________________________________________[/cyan]" )
        self.Console.print( f"Converting Media newer than {self.Age_Convert} days old" )
        self.Console.print( f"Working on the following file types:\t" )

        for Key, Values in self.Data_Types.items():
            self.Console.print( f"\t{Key}\t{Values}" )

    #---------------------------------------------------------------------------------------------------------------#
    # Add an existing directory to the list of directories to be processed
    # Returns nothing
    #---------------------------------------------------------------------------------------------------------------#
    def Add_Directory( self, Directory ):

        if ( os.path.exists( Directory ) ):
            self.Media["Directories"].append( Directory )
        else:
            self.Console.print( f"Error: The directory does not exist: {Directory}", style="red" )


    #---------------------------------------------------------------------------------------------------------------#
    # Replace narrow no-break spaces and review filenames that exceed the configured path-length limit
    # Returns the current file path after any filename changes
    #---------------------------------------------------------------------------------------------------------------#
    def Ensure_Filename( self, Full_Path ):
        New_Path = Full_Path

        # Define the narrow no-break space character and the normal space.
        Narrow_space = "\u202F"
        Normal_space = " "
        # Check if the file path contains the narrow no-break space
        if ( Narrow_space in Full_Path ):
            # Create a new filename by replacing narrow no-break spaces with normal spaces
            New_Path = Full_Path.replace( Narrow_space, Normal_space )

            try:
                self.Console.print( f"[yellow]Found Narrow_Space in filename.  Renaming:\n{New_Path}", style="yellow" )
                os.rename( Full_Path, New_Path )
                #return new_file_path
                Full_Path = New_Path
            except Exception as e:
                self.Console.print( f"Error replacing the unicode SPACE:\n{e}\nFile: {Full_Path}", style="red" )
                #return file_path

        Filename = os.path.basename( Full_Path )
        Name, Extension = os.path.splitext( Filename )
        Directory = os.path.dirname( Full_Path )
        if ( os.path.isfile( Full_Path ) and len( Full_Path ) > self.FILENAME_LIMIT ):
            #self.Console.print( f"Old Filename: {Filename}", style="yellow" )
            #Base_name = Name[:self.FILENAME_LIMIT  - 10 - len( Extension ) - 8]  # Leave room for extension and UUID suffix
            Base_name = Full_Path[:self.FILENAME_LIMIT  - 10 - len( Extension ) - 8]  # Leave room for extension and UUID suffix
            Unique_Suffix = str( uuid.uuid4() )[:8]  # Generate a short unique ID
            # TODO: Review long filename handling. New_Name is calculated but is not currently used.
            New_Name = f"{Base_name}_{Unique_Suffix}{Extension}"
            #self.Console.print( f"New Filename: {New_Name}", style="yellow" )
            #New_Path = os.path.join( Directory, New_Name )
            os.rename( Full_Path, New_Path )
        
        return New_Path


    #---------------------------------------------------------------------------------------------------------------#
    # Recursively scan the configured directories, filter files by age, and categorize them by media type
    # Creates progress tasks for each supported file category
    # Returns nothing
    #---------------------------------------------------------------------------------------------------------------#
    def Build_File_List( self ):
        print()
        self.Console.print( f"Scanning the following Directories" )
        self.Progress.Start( "Overall Status", "Files" )

        for directory in self.Media["Directories"]:
            self.Console.print( f"\t{directory}" )
            Directory_Files = glob.glob( directory + os.sep + "/**/*.*", recursive=True )


            for File in Directory_Files:
                File_Modified_date = datetime.fromtimestamp( os.path.getmtime( File ) )
                Age = self.Today - File_Modified_date
                if ( Age.days < self.Age_Convert ):

                    # Fix filenames
                    File = self.Ensure_Filename( File )
                    if ( "\u202F" in File ):
                        self.Console.print( f"*** - Filename still contains Narrow SPACE\n{File}\n" )

                    self.Media["Files"].append( File )
                    Filename_Extension = os.path.splitext( File )[1].lower()

                    # Optional debugging: log the file and its extension
                    #self.Console.print(f"Processing file: {file} with extension: {filename_extension}")

                    if ( Filename_Extension in self.Data_Types["Deletes"] ):
                        if ( len(self.Media["Deletes"]) == 0 ):
                            self.Tasks["Deletes"] = self.Progress.Add_Task("Deletes", Total=0)
                        self.Media["Deletes"].append( File )
                    elif Filename_Extension in self.Data_Types["Movies"]:
                        if len(self.Media["Movies"]) == 0:
                            self.Tasks["Movies"] = self.Progress.Add_Task("Movies", Total=0)
                        self.Media["Movies"].append( File )
                    elif Filename_Extension in self.Data_Types["Images"]:
                        if len(self.Media["Images"]) == 0:
                            self.Tasks["Images"] = self.Progress.Add_Task("Images", Total=0)
                        self.Media["Images"].append( File )
                    else:
                        if ( len( self.Media["Others"] ) == 0 ):
                            self.Tasks["Others"] = self.Progress.Add_Task( "Others", Total=0 )
                        self.Media["Others"].append( File )

        if ( len(self.Media["Files"]) == 0 ):
            self.Console.print( f"\tNo files were found to process.", style="yellow" )
        else:
            # Files found
            self.Console.print(f"Found the following data: ")
            if ( "Deletes" in self.Tasks and self.Tasks["Deletes"] is not None ):
                self.Progress.Update_Task( self.Tasks["Deletes"], Total=len(self.Media["Deletes"]) )
                self.Console.print( f"\tDeletes: {len(self.Media['Deletes'])}" )
            if ( "Images" in self.Tasks and self.Tasks["Images"] is not None ):
                self.Progress.Update_Task( self.Tasks["Images"], Total=len(self.Media["Images"]) )
                self.Console.print( f"\tImages: {len(self.Media['Images'])}")
            if ( "Movies" in self.Tasks and self.Tasks["Movies"] is not None ):
                self.Progress.Update_Task( self.Tasks["Movies"], Total=len(self.Media["Movies"]) )
                self.Console.print( f"\tMovies: {len(self.Media['Movies'])}" )
            if ( "Others" in self.Tasks and self.Tasks["Others"] is not None ):
                self.Progress.Update_Task( self.Tasks["Others"], Total=len(self.Media["Others"]) )
                self.Console.print( f"\tOthers: {len(self.Media['Others'])}" )

    #---------------------------------------------------------------------------------------------------------------#
    # Begin looping through data
    # Process categorized deletions, images, and movies using separate thread pools
    # Stops launching additional work when a processing thread sets Stop_Due_to_Error
    # Returns nothing
    #---------------------------------------------------------------------------------------------------------------#
    def Process_Files( self ):
        self.Console.print( f"[cyan]__________________________________________________________________________________[/cyan]" )
        self.Console.print( f"[cyan] Processing Files less than {self.Age_Convert} days old[/cyan]" )
        self.Console.print( f"[cyan]__________________________________________________________________________________[/cyan]" )


        if ( len( self.Media["Deletes"] ) > 0 ):
            with ThreadPoolExecutor( max_workers = self.Threads["Deletes"] ) as pool:
                self.Progress.Update_Task( self.Tasks["Deletes"], Visible=True )
                for File in self.Media["Deletes"]:
                    # Launch Thread - calls function
                    if ( not self.Stop_Due_to_Error ):
                        pool.submit( self.Thread_Delete, File )
            self.Progress.Update_Task( self.Tasks["Deletes"], Visible=False )

        if ( len( self.Media["Images"] ) > 0 ):
            with ThreadPoolExecutor( max_workers = self.Threads["Images"] ) as pool:
                self.Progress.Update_Task( self.Tasks["Images"], Visible=True )
                for File in self.Media["Images"]:
                    # Launch Thread - calls function
                    if ( not self.Stop_Due_to_Error ):
                        pool.submit( self.Thread_Image, File )
            self.Progress.Update_Task( self.Tasks["Images"], Visible=False )

        if ( len( self.Media["Movies"] ) > 0 ):
            with ThreadPoolExecutor( max_workers = self.Threads["Movies"] ) as pool:
                self.Progress.Update_Task( self.Tasks["Movies"], Visible=True )
                for File in self.Media["Movies"]:
                    # Launch Thread - calls function
                    if ( not self.Stop_Due_to_Error ):
                        pool.submit( self.Thread_Movie, File )
            self.Progress.Update_Task( self.Tasks["Movies"], Visible=False )

        if ( self.Stop_Due_to_Error ):
            self.Console.print( f"\nAll threads have been stopped due to an error", style="bright_red" )
            #self.Report()


    #---------------------------------------------------------------------------------------------------------------#
    # Delete one configured file and advance the deletion progress task
    # Logs an error if the deletion cannot be completed
    # Returns nothing
    #---------------------------------------------------------------------------------------------------------------#
    def Thread_Delete( self, File ):
        try: 
            Filename = os.path.basename( File )
            self.Console.print( f"\tDeleting: {Filename}", style="cyan" )
            self.Delete_File_With_Retries( File )

            self.Progress.Update_Task( self.Tasks["Deletes"], Advance=1 )

        except Exception as e:
            self.Console.print( f"An error has occurred in Thread_Delete():\n\t{str(e)}", style="red" )
            self.Stop_Due_to_Error = True
            return


    #---------------------------------------------------------------------------------------------------------------#
    # Process one image file by renaming, converting, preserving metadata, and resizing when required
    # Supports existing WebP files, HEIC files, NEF files, and other configured image formats
    # Returns nothing
    #---------------------------------------------------------------------------------------------------------------#
    def Thread_Image( self, File ):
        try:
            if ( self.Stop_Due_to_Error ):
                return

            Filename = os.path.basename( File )
            Filename_Extension = os.path.splitext( File )[1]
            Filename_Base = os.path.splitext( Filename )[0]
            File_Size_Original = os.path.getsize( File )
            Directory = os.path.dirname( File )
            Directory_Parent = os.path.basename( Directory )
            #Resize_Taskname = Filename
            Resize_Taskname = File

            File_Modified_date = datetime.fromtimestamp( os.path.getmtime( File ) )
            Age = self.Today - File_Modified_date

            self.Tasks[f"{File}"] = self.Progress.Add_Task( f"{Filename}", Total=3 )
            self.Progress.Update_Task( self.Tasks[f"{File}"], Visible=True )

            if ( Age.days < self.Age_Convert ):

                Filename_New = Filename

                if ( Filename_Extension.lower() == ".webp" ):
                    try:
                        File_Modify_Date = self.Get_File_Date( File )

                        if ( File_Modify_Date ):
                            Date_Prefix = f"{File_Modify_Date} - "

                            Filename_Base_Clean = self.Remove_Date_Prefix( Filename_Base )
                            Filename_Base_Clean = self.Remove_Trailing_Counter( Filename_Base_Clean )

                            Filename_Expected = f"{Date_Prefix}{Filename_Base_Clean}.webp"

                            if ( Filename != Filename_Expected ):
                                Filename_New = self.Get_Unique_Filename(
                                    Directory=Directory,
                                    Filename_Base=Filename_Base_Clean,
                                    Filename_Extension=".webp",
                                    Date=Date_Prefix
                                )

                                os.rename(
                                    File,
                                    os.path.join( Directory, Filename_New )
                                )

                    except Exception as e:
                        self.Console.print(
                            f"Unable to rename: {File}\n{e}",
                            "Error"
                        )
                        self.Stop_Due_to_Error = True
                        return

                elif ( Filename_Extension.lower() in self.Data_Types["Images_Convert"] ):
                    #self.Console.print( f"\t[gray]Converting:[/] [[\{Directory_Parent}]]\t{Filename}" )
                    self.Console.print( f"\t[grey35]Converting: \\[\\[{Directory_Parent}]][/]\t{Filename}" )

                    File_Modify_Date = self.Get_File_Date( File )

                    Date_Prefix = ""
                    if ( File_Modify_Date ):
                        Date_Prefix = f"{File_Modify_Date} - "

                    Filename_Base_Clean = self.Remove_Date_Prefix( Filename_Base )
                    Filename_Base_Clean = self.Remove_Trailing_Counter( Filename_Base_Clean )

                    Filename_New = self.Get_Unique_Filename(
                        Directory=Directory,
                        Filename_Base=Filename_Base_Clean,
                        Filename_Extension=".webp",
                        Date=Date_Prefix
                    )

                    Path_New = os.path.join( Directory, Filename_New )

                    if ( Filename_Extension.lower() == ".heic" ):
                        try:
                            with WandImage( filename=File ) as img:
                                img.format = "webp"
                                img.compression_quality = 100
                                img.options["webp:lossless"] = "true"
                                img.save( filename=Path_New )

                        except Exception as e:
                            self.Console.print( f"Error processing: {File}\n{e}", style="red" )
                            self.Stop_Due_to_Error = True
                            return

                    # If .nef, Extract the embedded JpgFromRaw image with ExifTool and convert it to WebP
                    elif ( Filename_Extension.lower() == ".nef" ):
                        Temp_Dir_NEF = None

                        try:
                            Temp_Dir_NEF = tempfile.mkdtemp()
                            Temp_Path_JPG = os.path.join( Temp_Dir_NEF, "JpgFromRaw.jpg" )

                            cmd = [
                                self.ExifTool,
                                "-b",
                                "-JpgFromRaw",
                                File
                            ]

                            with open( Temp_Path_JPG, "wb" ) as Temp_File:
                                cmd_Result = subprocess.run(
                                    cmd,
                                    stdout=Temp_File,
                                    stderr=subprocess.PIPE
                                )

                            if ( cmd_Result.returncode != 0 ):
                                Status = cmd_Result.stderr

                                if ( isinstance( Status, bytes ) ):
                                    Status = Status.decode( "utf-8", errors="replace" )

                                raise Exception(
                                    f"Unable to extract JpgFromRaw:\n{Status}"
                                )

                            if (
                                not os.path.exists( Temp_Path_JPG )
                                or os.path.getsize( Temp_Path_JPG ) == 0
                            ):
                                raise Exception(
                                    "ExifTool did not extract a valid JpgFromRaw image."
                                )

                            with PILImage.open( Temp_Path_JPG ) as img:
                                img.load()

                                img.save(
                                    Path_New,
                                    "WEBP",
                                    quality=100,
                                    method=6
                                )

                        except Exception as e:
                            self.Console.print( f"Error processing: {File}\n{e}", style="red" )
                            self.Stop_Due_to_Error = True
                            return

                        finally:
                            if ( Temp_Dir_NEF and os.path.exists( Temp_Dir_NEF ) ):
                                shutil.rmtree( Temp_Dir_NEF )

                    else:
                        cmd = (
                            f"{self.FFMpeg} "
                            f"-hide_banner "
                            f"-loglevel error "
                            f"-i \"{File}\" "
                            f"-c:v libwebp "
                            f"-lossless 1 "
                            f"-compression_level 6 "
                            f"\"{Path_New}\""
                        )

                        cmd_Result = subprocess.run(
                            cmd,
                            shell=True,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE
                        )

                        if ( cmd_Result.returncode != 0 ):
                            Status = cmd_Result.stderr

                            if ( isinstance( Status, bytes ) ):
                                Status = Status.decode( "utf-8" )

                            self.Console.print( f"Error in Thread_Image(), performing conversion:\n" f"{cmd}\n\n{Status}", style="red" )
                            self.Stop_Due_to_Error = True
                            return

                    if ( not os.path.exists( Path_New ) ):
                        self.Console.print( f"Converted WebP file was not created:\n{Path_New}", style="red" )
                        self.Stop_Due_to_Error = True
                        return

                    try:
                        self.Write_Metadata( File, Path_New )

                    except Exception as e:
                        self.Console.print( f"Unable to copy metadata to:\n{Path_New}\n{e}", style="red" )
                        self.Delete_File_With_Retries( Path_New )
                        self.Stop_Due_to_Error = True
                        return

                    Original_Stat = os.stat( File )
                    os.utime(
                        Path_New,
                        ( Original_Stat.st_atime, Original_Stat.st_mtime )
                    )

                    self.Delete_File_With_Retries( File )

                else:
                    self.Console.print( f"Unsupported image type: {File}", style="yellow" )
                    return

                if ( not self.Image_Resize(
                    Resize_Taskname,
                    Directory,
                    Filename_New,
                    File_Size_Original
                ) ):
                    self.Console.print(  f"An error has occurred in Thread_Image():\n" f"\tFilename not resized", style="red" )
                    self.Stop_Due_to_Error = True

            self.Progress.Complete_Task( self.Tasks[f"{File}"] )
            self.Progress.Update_Task( self.Tasks["Images"], Advance=1 )
            self.Progress.Update_Task(
                self.Tasks[f"{File}"],
                Visible=False
            )

        except Exception as e:
            self.Console.print( f"An error has occurred in Thread_Image():\n\t{str(e)}", style="red" )
            self.Stop_Due_to_Error = True

            if ( File in self.Tasks ):
                self.Progress.Update_Task(
                    self.Tasks[f"{File}"],
                    Visible=False
                )




    #---------------------------------------------------------------------------------------------------------------#
    # Process one movie file by normalizing its extension, converting supported formats, and preserving metadata
    # Updates the movie progress task and accumulated file-size totals
    # Returns nothing
    #---------------------------------------------------------------------------------------------------------------#
    def Thread_Movie( self, File ):
        try: 
            if ( self.Stop_Due_to_Error ):
                return
            Filename           = os.path.basename( File )
            Filename_Extension = os.path.splitext( File )[1]
            Filename_Base      = os.path.splitext( Filename )[0]
            Directory = os.path.dirname(  File ) 
            Directory_Parent = os.path.basename( Directory )

            File_Modified_date = datetime.fromtimestamp( os.path.getmtime( File ) )
            Age = self.Today - File_Modified_date
            
            if ( Age.days < self.Age_Convert ):
                # File is within the age limit
                Filename_New = self.Get_Unique_Filename( Directory=Directory, Filename_Base=Filename_Base, Filename_Extension=Filename_Extension )
                
                if ( Filename_Extension == ".MP4" ):
                    # Rename to .mp4
                    self.Console.print( f"Renaming Extension on: {File}" )
                    try:
                        Filename_New = Filename_Base + Filename_Extension.lower()
                        os.rename( File, os.path.join( Directory, Filename_New ) )  # not renaming the file, only changing the extension
                    except Exception as e:
                        self.Console.print( f"Unable to rename: {File}", style="red" )
                if ( Filename_Extension.lower() in self.Data_Types["Movies_Convert"] ):
                    self.Console.print( f"[gray]Converting: /{Directory_Parent}[/]\t{Filename_Base + Filename_Extension}" )
                    
                    Parser = createParser( File )

                    if ( Parser ):
                        File_Size_Before = os.path.getsize( File )
                        self.Size_Before = self.Size_Before + File_Size_Before

                        # Attempt to extract metadata.  If not found, set to null
                        try:
                            Metadata = extractMetadata( Parser )
                        except Exception as e:
                            self.Console.print( f"Unable to extract Metadata\n{e}", style="red" )
                            Metadata = None

                        for Info in Metadata.exportPlaintext():
                                if ( Info.split(':')[0] == '- Creation date' ):
                                    Date_Temp = Info.partition( "date: " )[2]
                                    Date_Object = datetime.strptime( Date_Temp, "%Y-%m-%d %H:%M:%S" )
                                    #Date_Metadata = str( Date_Object.year ) + "-" + str( Date_Object.month ) + "-" + str( Date_Object.day ) + "_" + str( Date_Object.hour ) + "-" + str( Date_Object.minute ) + "-" + str( Date_Object.second )
                                    Date_Metadata = f"{Date_Object.year}-{Date_Object.month}-{Date_Object.day}_{Date_Object.hour}-{Date_Object.minute}-{Date_Object.second}"
                        Parser.stream._input.close()
                        #Final_Filename = Filename_Base + "-" + Date_Metadata + ".mp4"
                        Filename_New = self.Get_Unique_Filename( Directory=Directory, Filename_Base=f"{Filename_Base}-{Date_Metadata}", Filename_Extension=".mp4" )
                        # Attempting to convert the file
                        cmd = f"{self.FFMpeg} -hide_banner -loglevel error -i \"{File}\" \"{os.path.join( Directory, Filename_New )}\" -map_metadata 1"
                        cmd_Result = subprocess.run( cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE )
                        #print( cmd_Result )

                        if ( cmd_Result.returncode != 0 ):
                            Status = cmd_Result.stderr #.decode('utf-8')
                            if ( isinstance( Status, bytes ) ):
                                Status = Status.decode('utf-8')
                            #Status = cmd_Result.stderr #.decode('utf-8')
                            self.Console.print( f"Error in Thread_Movie(), performing conversion:\n{cmd}\n\n{Status}", style="red" )
                            self.Stop_Due_to_Error = True
                            return
                        else:
                            if ( os.path.isfile( os.path.join( Directory, Filename_New ) ) ):
                                # Copy the original metadata to the new file ( ex: preserve the create date )
                                cmd = f"{self.ExifTool} -q -overwrite_original -ee -TagsFromFile \"{File}\" \"-FileCreateDate<CreationDate\" \"-CreateDate<CreationDate\" \"-ModifyDate<CreationDate\" \"{os.path.join(Directory, Filename_New)}\""
                                #self.Console.print( f"cmd: {cmd}")
                                cmd_Result = subprocess.run( cmd, shell=True, stdout=subprocess.PIPE,stderr=subprocess.PIPE )
                                if ( cmd_Result.returncode != 0 ):
                                    Status = cmd_Result.stderr #.decode('utf-8')
                                    if ( isinstance( Status, bytes ) ):
                                        Status = Status.decode('utf-8')
                                    #Status = cmd_Result.stderr #.decode('utf-8')
                                    self.Console.print( f"Error in Thread_Movie(), writing metadata:\n{cmd}\n\n{Status}", style="red" )
                                    self.Delete_File_With_Retries( os.path.join( Directory, Filename_New ) )
                                    self.Stop_Due_to_Error = True
                                    return
    
                                self.Delete_File_With_Retries( File )
                                File_Size_After = os.path.getsize( os.path.join( Directory, Filename_New ) )
                                # TODO - put a lock on this to ensure proper reporting
                                self.Size_After = self.Size_After + File_Size_After


                    else:
                        self.Console.print( f"Unable to parse file for metadata", style="red" )
                        self.Stop_Due_to_Error = True
                        return
                   

            self.Progress.Update_Task( self.Tasks["Movies"], Advance=1 )

        except Exception as e:
            self.Console.print( f"An error has occurred in Thread_Movie():\n\t{File}\n\t{str(e)}", style="red" )
            self.Stop_Due_to_Error = True


    #---------------------------------------------------------------------------------------------------------------#
    # Resize an image when it exceeds the configured dimensions while preserving metadata and timestamps
    # Replaces the original image only after the resized file and metadata have been verified
    # Returns True when processing completes, or False when an error occurs
    #---------------------------------------------------------------------------------------------------------------#
    def Image_Resize( self, Resize_Taskname, Directory, Filename_Original, File_Size_Original  ):
        # 1 - Extract metadata using Exiftool
        # 2 - Use Pillow to resize the file
        # 3 - Write Metadata from original file to new
        # 4 - Verify before removing the old file.

        try:
            Section = "Start" # Used in Exception

            Path_Original = os.path.join( Directory, Filename_Original )
            Saved_Filename_Original = Path_Original
            Filename_Base, Filename_Extension = os.path.splitext( os.path.basename( Path_Original ) )

            
            # ExifTool is having trouble with filenames > 140.  
            # It is incorrectly failing with a "File Not Found" error
            # Using a temp directory and filename for resizing functions
            Temp_Dir = tempfile.mkdtemp()
            Temp_Path_Original = None
            Temp_Path_New = None

            Filename_Final = None


            # Create a short temporary path and copy the original file into the temporary directory
            Temp_Path_Original = os.path.join( Temp_Dir, f"original{Filename_Extension}" )
            shutil.copy2( Path_Original, Temp_Path_Original )


            # Step 1: Extract Metadata using ExifTool
            Section = "Step 1"

            #print(f"Extracting metadata from {Temp_Filename_Original}")
            Metadata = self.Extract_Metadata( Temp_Path_Original )

            if ( not Metadata ):
                self.Console.print(f"No Metadata found in {Saved_Filename_Original}. Skipping resize.", style="red" )
                # remove temporary directory and files
                if ( Temp_Dir ):
                    shutil.rmtree( Temp_Dir )
                self.Stop_Due_to_Error = True
                return False

            Section = "Metadata exists"

            # Extract dimensions from the metadata instead of using ffprobe
            Check_Width = Metadata.get( 'ImageWidth', 0 )
            Check_Height = Metadata.get( 'ImageHeight', 0 )

            #self.Console.print( f"[cyan]Path_Original: {Path_Original}[/cyan]", style="cyan" )
            #self.Console.print( f"[cyan]Saved_Filename_Original: {Saved_Filename_Original}[/cyan]", style="cyan" )


            File_Modify_Date = self.Get_File_Date( Path_Original, Metadata )


            Section = "Compare Dimensions"
            if ( Check_Width and Check_Height ):

                if ( Check_Width > self.Width_Limit or Check_Height > self.Height_Limit ):
                    #self.Console.print(f"Resizing image {Filename}: Width={Check_Width}, Height={Check_Height}", style="cyan" )
                    #self.Console.print( f"\tWidth: {Check_Width}\tHeight: {Check_Height}\t{Path_Original}", style="cyan" )
                    #File_Size_Before = os.path.getsize( Temp_Path_Original )
                    File_Size_Before = File_Size_Original
                    self.Size_Before = self.Size_Before + File_Size_Before

                    
                    # Step 2: Resize Image using Pillow
                    Section = "Step 2"
                    #Filename_Final = self.Get_Unique_Filename( Directory=Directory, Filename_Base=Filename_Base, Filename_Extension=".jpg", Date=f"{File_Modify_Date} - " )
                    Filename_Final = self.Get_Unique_Filename( Directory=Directory, Filename_Base=Filename_Base, Filename_Extension=Filename_Extension, Date=f"{File_Modify_Date} - " )
                    Filename_Final = os.path.join( Directory, Filename_Final )
                    Temp_Path_New = os.path.join( Temp_Dir, f"resize{Filename_Extension}" )

                    #self.Console.print( f"[cyan]Filename_Final: {Filename_Final}[/cyan]", style="cyan" )


                    #Original_Filename_New = Filename_New  # ??

                    # Resize the image while maintaining aspect ratio
                    #print(f"Resizing image as {Filename_Final}")
                    #self.Console.print( f"Resizing image as {Filename_Final}", style="cyan )
                    # Resizing the temporary file in the temporary directory
                    self.Resize_Image_with_PIL( Temp_Path_Original, Temp_Path_New, Path_Original )

                    # Step 3: Write Metadata back to resized image using ExifTool
                    Section = "Step 3"
                    #print(f"Writing metadata back to {Filename_New}")
                    self.Write_Metadata( Temp_Path_Original, Temp_Path_New )
                    #self.Progress.Update_Task( self.Tasks[f"{Resize_Taskname}"], Advance=1 )

                    # Step 4: Verify that metadata exists and cleanup
                    Section = "Verification - Extract Metadata"
                    Test = self.Extract_Metadata( Temp_Path_New )
                    Section = "Verification - Copy temp file to final location"
                    shutil.copy2( Temp_Path_New, Filename_Final )
                    Section = "Verification - temporary file retained until temp directory cleanup"
                    #os.remove( Temp_Path_New ) # done when temp_dir is removed

                    Section = "Timestamps"
                    if ( Test ):
                        # Copy original timestamps
                        Section = f"Timestamps - A"
                        Original_stat = os.stat( Path_Original )
                        Section = f"Timestamps - B"
                        os.utime( Filename_Final, ( Original_stat.st_atime, Original_stat.st_mtime ) )
                        Section = f"Timestamps - C"
                        # Remove old file and replace it with the resized one
                        self.Delete_File_With_Retries( Path_Original )
                        #self.Console.print( f"Filename_New = {Filename_New}")
                        #self.Console.print( f"Path_Check = {Path_Check}")
                        Section = f"Timestamps - D"
                        os.rename( Filename_Final, Path_Original )  # may need to put this back
                        #self.Console.print(f"Resized image: {Filename}" )
                        File_Size_After = os.path.getsize( Path_Original )
                        # TODO - put a lock on this to ensure proper reporting
                        self.Size_After  = self.Size_After + File_Size_After
                        if ( File_Size_After < File_Size_Before ):
                            Size_Color = "green"
                        elif ( File_Size_After > File_Size_Before ):
                            Size_Color = "red"
                        else:
                            Size_Color = "yellow"

                        self.Console.print(
                            f"\tResized:"
                            f"\t[grey35]Pre:[/] {self.Human_Readable_Size( File_Size_Before )}"
                            f"\t[grey35]Post:[/] [{Size_Color}]{self.Human_Readable_Size( File_Size_After )}[/{Size_Color}]"
                            f"\t - {Filename_Original}"
                        )

                    else:
                        self.Delete_File_With_Retries( Filename_Final )
                        self.Console.print(f"Failed to verify metadata for {Filename_Final}. Original retained.", style="red" )
                    
                    self.Progress.Update_Task( self.Tasks[f"{Resize_Taskname}"], Advance=1 )
                
                self.Progress.Update_Task( self.Tasks[f"{Resize_Taskname}"], Advance=1 )

            else:
                self.Console.print( f"Unable to determine Width or Height on {Path_Original}", style="yellow" )
                self.Stop_Due_to_Error = True
                self.Console.print( f"Metadata: {Metadata}", style="yellow" )
                
            self.Progress.Update_Task( self.Tasks[f"{Resize_Taskname}"], Advance=1 )            

            if ( Temp_Dir ):
                shutil.rmtree( Temp_Dir )
            return True
        except Exception as e:
            self.Stop_Due_to_Error = True
            self.Console.print(f"An Error has occurred in Image_Resize() - {Section}:\n\t{Path_Original}\n\t{e}", style="red" )
            if ( Temp_Dir ):
                shutil.rmtree( Temp_Dir )
            if ( Temp_Path_Original ):
                self.Console.print( f"Temp_Path_Original: {Temp_Path_Original}", style="yellow" )
            # Debugging only
            #if ( Temp_Path_New ):
            #    self.Console.print( f"Temp_Path_New: {Temp_Path_New}", style="yellow"  )
            #if ( File_Modify_Date ):
            #    self.Console.print( f"File_Modify_Date: {File_Modify_Date}", style="yellow"  )
            #if ( Filename_Final ):
            #    self.Console.print( f"Filename_Final: {Filename_Final}", style="yellow"  )

            return False


    #---------------------------------------------------------------------------------------------------------------#
    # Get the preferred metadata date for files located within a Games directory
    # Falls back to the file modification date when a usable metadata date is unavailable
    # Returns the date as YYYY-MM-DD, or None when the file is not within a Games directory
    #---------------------------------------------------------------------------------------------------------------#
    def Get_File_Date( self, Path_File, Metadata=None ):
        try:

            Date_Fields = [
                "DateTimeOriginal",  # EXIF - best (Date Taken)
                "DateCreated",       # IPTC
                "CreateDate",        # XMP
                "ModifyDate",        # fallback
                "FileCreationDate",  # last resort
            ]

            if ( not Metadata ):
                # get it
                Metadata = self.Extract_Metadata( Path_File )
                if ( not Metadata ):
                    raise Exception( f"Error extracting metadata (a):\n\t{Path_File}" )


            # If the file is in a Games directory, return YYYY-MM-DD for use as a filename prefix
            Path_Parts = os.path.normpath( Path_File ).split( os.sep )
            if ( any( Path_Part.lower() == "games" for Path_Part in Path_Parts ) ):

            #if ( "games".lower() in Path_File.lower() ):

                File_Modify_Date = ""

                for Date_Field in Date_Fields:
                    File_Modify_Date = Metadata.get( Date_Field, "" )
                    if ( File_Modify_Date ):
                        break

                try:
                    if ( File_Modify_Date ):
                        File_Modify_Date = File_Modify_Date.split(" ")[0].replace(":", "-")
                    else:
                        File_Modify_Date = datetime.fromtimestamp(
                            os.path.getmtime( Path_File )
                        ).strftime('%Y-%m-%d')

                except Exception:
                    File_Modify_Date = datetime.fromtimestamp(
                        os.path.getmtime( Path_File )
                    ).strftime('%Y-%m-%d')

            else: 
                File_Modify_Date = None

            return File_Modify_Date

        except Exception as e:
            self.Console.print( f"An Error has occurred in Get_File_Date():\n\t{e}", style="red"  )
            self.Stop_Due_to_Error = True


    #---------------------------------------------------------------------------------------------------------------#
    # Extract file metadata as JSON using ExifTool
    # Uses an ExifTool argument file as a fallback when the direct path cannot be read
    # Returns the metadata dictionary, or an empty dictionary when no metadata is returned
    #---------------------------------------------------------------------------------------------------------------#
    def Extract_Metadata( self, Path_Input_File ):
        try:
            #self.Console.print( f"DEBUGGING D" )
            if ( not os.path.exists( Path_Input_File ) ):
                self.Console.print( f"File not found: {Path_Input_File}", style="red"  )
                self.Stop_Due_to_Error = True
                raise Exception( f"File not found: {Path_Input_File}" )

            # Normalize the path
            Path_Input_File = os.path.normpath( Path_Input_File )

            # Try the normal method first
            cmd = f'{self.ExifTool} -charset filename=UTF8 -json "{Path_Input_File}"'
            result = subprocess.run( cmd, shell=True, capture_output=True, text=True, encoding="utf-8", errors="replace" )
            
            if ( result.returncode == 0 ):
                metadata = json.loads( result.stdout )[0]
                if metadata:
                    return metadata
                else:
                    self.Console.print( f"No metadata returned: {Path_Input_File}", style="yellow"  )
                    return {}
            else:
                # Check for "file not found" error in the stderr
                # This is most likely due to Unicode characters in the filename or directory path
                # ExifTool handles this by reading the full path from an argument file
                if ( result.stderr and "file not found" in result.stderr.lower() ):
                    #self.Console.print( f"Normal method failed with 'file not found'. Falling back to text file method for:\n{Path_Input_File}", style="yellow"  )

                    # Create a temporary file to store the full path
                    with tempfile.NamedTemporaryFile( mode="w", encoding="utf-8", delete=False, suffix=".txt" ) as tf:
                        tf.write(Path_Input_File)
                        temp_txt = tf.name

                    # Build the fallback command using -@ parameter.
                    cmd = f'{self.ExifTool} -charset filename=UTF8 -@ "{temp_txt}" -json'
                    result = subprocess.run( cmd, shell=True, capture_output=True, text=True, encoding="utf-8", errors="replace" )
                    
                    # Clean up the temporary file.
                    #os.remove( temp_txt )
                    self.Delete_File_With_Retries( temp_txt )

                    if ( result.returncode == 0 ):
                        metadata = json.loads( result.stdout )[0]
                        if ( metadata ):
                            return metadata
                        else:
                            self.Console.print( f"No metadata returned (fallback method): {Path_Input_File}", style="yellow" )
                            return {}

                    else:
                        self.Stop_Due_to_Error = True
                        raise Exception( f"Error extracting metadata (fallback):\n{result.stderr}\n{Path_Input_File}" )

                else:
                    # An error, but not "file not found"
                    self.Stop_Due_to_Error = True
                    raise Exception(f"Error extracting metadata.  Not a 'file not found' error:\n{result.stderr}\n{Path_Input_File}")

                
        except Exception as e:
            self.Console.print( f"An Error has occurred in Extract_Metadata():\n\t{e}", style="red"  )
            self.Stop_Due_to_Error = True
            #raise Exception( f"Error extracting metadata (c):\n{result.stderr}\n{Path_Input_File}\n{cmd}" )
            raise

    #---------------------------------------------------------------------------------------------------------------#
    # Copy metadata from an input file to an output file using ExifTool
    # Retries when a PermissionError or OSError occurs while running the command
    # Returns True when the metadata is written successfully
    #---------------------------------------------------------------------------------------------------------------#
    def Write_Metadata(self, Path_Input, Path_Output, Max_Retries=5, Retry_Delay=10):
        cmd = f'{self.ExifTool} -overwrite_original -TagsFromFile "{Path_Input}" -all:all "{Path_Output}"'
        
        for attempt in range(Max_Retries):
            try:
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

                if ( result.returncode == 0 ):
                    return True
                else:
                    raise Exception(f"Error writing metadata: {result.stderr}")

            except (PermissionError, OSError) as e:
                # Check if the error is related to the file being in use
                if ( attempt < Max_Retries - 1 ):
                    print(f"File is currently in use. Retrying in {Retry_Delay} seconds... (Attempt {attempt + 1}/{Max_Retries})")
                    sleep( Retry_Delay )
                else:
                    raise Exception(f"Error writing metadata after {Max_Retries} attempts: {str(e)}")

        raise Exception(f"Failed to write metadata after {Max_Retries} retries.")

    #---------------------------------------------------------------------------------------------------------------#
    # Resize an image with Pillow while preserving its aspect ratio and configured dimension limits
    # Writes the resized image to the supplied output path as WebP
    # Returns nothing
    #---------------------------------------------------------------------------------------------------------------#
    def Resize_Image_with_PIL( self, Path_Input, Path_Output, Path_Reporting_Only ):
        try:
            with PILImage.open( Path_Input ) as img:
                img.load()
                Image_Width, Image_Height = img.size
                Aspect_Ratio = Image_Width / Image_Height

                # Default: no resizing (shouldn't happen because the function is only called if one is over the limit)
                New_Width, New_Height = Image_Width, Image_Height

                # Check which dimension(s) exceed their limits
                Over_Width = Image_Width > self.Width_Limit
                Over_Height = Image_Height > self.Height_Limit

                if ( Over_Width and not Over_Height ):
                    # Only width exceeds limit
                    New_Width = self.Width_Limit
                    New_Height = int( New_Width / Aspect_Ratio )
                elif ( Over_Height and not Over_Width ):
                    # Only height exceeds limit
                    New_Height = self.Height_Limit
                    New_Width = int( New_Height * Aspect_Ratio )
                elif ( Over_Width and Over_Height ):
                    # Both exceed: choose the more restrictive scaling factor
                    Scale_Width = self.Width_Limit / Image_Width
                    Scale_Height = self.Height_Limit / Image_Height
                    if ( Scale_Width < Scale_Height ):
                        New_Width = self.Width_Limit
                        New_Height = int( New_Width / Aspect_Ratio )
                    else:
                        New_Height = self.Height_Limit
                        New_Width = int( New_Height * Aspect_Ratio )

                img = img.resize( ( New_Width, New_Height ), PILImage.LANCZOS )
                img.save(
                    Path_Output,
                    "WEBP",
                    #lossless=True,  # removed at this was creating a very large sized file without altering quality
                    quality=100,
                    method=6
                )

        except Exception as e:
            self.Console.print( f"An Error has occurred in Resize_Image_with_PIL():\n\t{e}\nOriginal: {Path_Reporting_Only}", style="red"  )
            self.Stop_Due_to_Error = True
    
    #---------------------------------------------------------------------------------------------------------------#
    # Copy metadata through temporary short filenames to avoid ExifTool path-length limitations
    # Restores the processed file to its original path and preserves its timestamps
    # Returns True when processing succeeds, or False when an error occurs
    #---------------------------------------------------------------------------------------------------------------#
    def Exiftool( self, Path_Input ):
        Test = False
        # Create a unique temporary directory
        Temp_Dir = tempfile.mkdtemp()

        # Create a short, unique name for the original file
        Temp_Filename_Original = os.path.join( Temp_Dir, "temp_original.jpg" )

        # Create a short, unique name for the processed file
        Temp_Filename_New = os.path.join( Temp_Dir, "temp_new.jpg" )

        # Copy the files to the temporary directory
        shutil.copy2( Path_Input, Temp_Filename_Original )
        shutil.copy2( Path_Input, Temp_Filename_New )

        try:

            cmd = f"{self.ExifTool} -q -overwrite_original -ee -TagsFromFile \"{Temp_Filename_Original}\" -all:all \"{Temp_Filename_New}\""
            cmd_Result = subprocess.run( cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True )

            if ( cmd_Result.returncode != 0 ):
                Status = cmd_Result.stderr #.decode('utf-8')
                #if ( isinstance( Status, bytes ) ):
                #    Status = Status.decode('utf-8')
                self.Console.print( f"Error in Exiftool(), writing metadata:\n[yellow]{cmd}[/yellow][red]\n\n{Status}[/red]" )
            else:
                # Get original file's timestamps
                Original_stat = os.stat( Path_Input )
                # Update the new file's timestamps to match the original
                os.utime( Temp_Filename_New, ( Original_stat.st_atime, Original_stat.st_mtime ) )
                # Copy the processed file back to its original location with the original name
                shutil.copy2( Temp_Filename_New, Path_Input )
                os.remove( Temp_Filename_New )
                #shutil.move( Temp_Filename_New, Path_Input )                
                Test = True

        except Exception as e:
            self.Console.print( f"An Error has occurred in Exiftool():\n\t{e}", style="red"  )
            self.Stop_Due_to_Error = True
            Test = False

        finally:
            shutil.rmtree( Temp_Dir )
            return Test



    #---------------------------------------------------------------------------------------------------------------#
    # Convert a file size in bytes into a human-readable value
    # Returns the formatted size using B, KB, MB, GB, TB, or PB
    #---------------------------------------------------------------------------------------------------------------#
    def Human_Readable_Size( self, size, decimal_places=2 ):
        try:
            for unit in ['B', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB']:
                if ( abs( size ) < 1024.0 or unit == 'PiB' ):
                    break
                size /= 1024.0
            return f"{size:.{decimal_places}f} {unit.replace( "i", "" )}"
        except Exception as e:
            print( f"An Error has occurred in Human_Readable_Size():\n\t{e}" )

    #---------------------------------------------------------------------------------------------------------------#
    # Remove one or more existing YYYY-MM-DD prefixes from a filename base
    # Returns the filename base without the date prefix
    #---------------------------------------------------------------------------------------------------------------#
    def Remove_Date_Prefix( self, Filename_Base ):
        try:
            #Filename_Base = re.sub( r"^\d{4}-\d{2}-\d{2}\s+-\s+", "", Filename_Base )
            Filename_Base = re.sub( r"^(?:\d{4}-\d{2}-\d{2}\s+-\s+)+", "", Filename_Base )
            return Filename_Base

        except Exception as e:
            self.Console.print( f"An Error has occurred in Remove_Date_Prefix():\n\t{e}", style="red"  )
            return Filename_Base

    #---------------------------------------------------------------------------------------------------------------#
    # Remove trailing "_1" or " 1" counters from a filename base
    # Returns the cleaned filename base
    #---------------------------------------------------------------------------------------------------------------#
    def Remove_Trailing_Counter( self, Filename_Base ):
        try:
            # Removes one or more trailing "_1" or " 1" patterns
            Filename_Base = re.sub( r"(?:_1| 1)+$", "", Filename_Base )
            return Filename_Base

        except Exception as e:
            self.Console.print( f"An Error has occurred in Remove_Trailing_Counter():\n\t{e}", style="red" )
            return Filename_Base
        
    #---------------------------------------------------------------------------------------------------------------#
    # Build a sanitized filename and append a counter when the requested filename already exists
    # Returns a unique filename without the directory path
    #---------------------------------------------------------------------------------------------------------------#
    def Get_Unique_Filename( self, Directory, Filename_Base, Filename_Extension, Max_Attempts=40, Date=None ):
        Counter = 0
        if ( not Date ):
            Date = ""
        
        # Remove non-ASCII characters from the filename
        # Normalize unicode and remove diacritics
        Filename_Base = unicodedata.normalize( "NFKD", Filename_Base ).encode("ascii", "ignore").decode("ascii")
        # Remove any remaining non-alphanumeric characters except spaces, periods, dashes, and underscores
        Filename_Base = re.sub( r'[^\w\s.-]', '', Filename_Base ).strip()
        

        # Check if the base filename already starts with the date
        if ( Filename_Base.startswith( Date ) ):
            Filename_New = Filename_Base + Filename_Extension
        else:
            Filename_New = Date + Filename_Base + Filename_Extension

        # Loop to find a unique filename
        while os.path.exists( os.path.join( Directory, Filename_New ) ):
            Counter += 1
            if ( Counter > Max_Attempts ):
                raise Exception(f"Error: Unable to find a unique filename after {Max_Attempts} attempts.")
            
            # Rename the file with a counter, but do not duplicate the date
            if ( Filename_Base.startswith( Date ) ):
                if ( len( Filename_Base ) > 180 ):
                    Filename_Base = Filename_Base[:180]
                Filename_New = f"{Filename_Base}_{Counter}{Filename_Extension}"
            else:
                if ( len( Filename_Base ) > 180 ):
                    Filename_Base = Filename_Base[:180]
                Filename_New = f"{Date}{Filename_Base}_{Counter}{Filename_Extension}"
        
        return Filename_New

    #---------------------------------------------------------------------------------------------------------------#
    # Display totals for processed directories and files, along with accumulated file-size results
    # Returns nothing
    #---------------------------------------------------------------------------------------------------------------#
    def Report( self ):
        print()
        self.Console.print( f"\tTotal Directories Processed: {len( self.Media['Directories'])}" )
        self.Console.print( f"\tTotal Files Processed: {len( self.Media['Files'])}" )
        self.Console.print( f"\tTotal Movies:  {len( self.Media['Movies'])}" )
        self.Console.print( f"\tTotal Images:  {len( self.Media['Images'])}" )
        self.Console.print( f"\tTotal Deletes: {len( self.Media['Deletes'] )}" )        
        self.Console.print( f"\tTotal Others:  {len( self.Media['Others'])}" )
        print()

        if ( self.Size_After < self.Size_Before ):
            Size_Color = "green"
        elif ( self.Size_After > self.Size_Before ):
            Size_Color = "red"
        else:
            Size_Color = "yellow"

        self.Console.print( f"\tTotal Size Before: {self.Human_Readable_Size( self.Size_Before )}" )
        self.Console.print( f"\tTotal Size After:  [{Size_Color}]{self.Human_Readable_Size( self.Size_After )}[/]" )
        self.Console.print( f"\tTotal Size Saved:  {self.Human_Readable_Size( self.Size_Before - self.Size_After )}" )
        print()


    #---------------------------------------------------------------------------------------------------------------#
    # Send a file to the Recycle Bin and retry when the operation temporarily fails
    # Logs an error when the file cannot be removed after the configured retries
    # Returns nothing
    #---------------------------------------------------------------------------------------------------------------#
    def Delete_File_With_Retries( self, File, Retries=3, Delay=2 ):
        # Normalize the path
        Path_Normalized = os.path.normpath( File )
        for Attempt in range( Retries ):
            try:
                #os.remove( File )
                send2trash( Path_Normalized )
                break
            except Exception as e:
                if ( Attempt < Retries - 1 ):
                    sleep( Delay )  # Wait before retrying
                else:
                    self.Console.print( f"Unable to delete: {Path_Normalized}\n\t{e}", style="red"  )


    #---------------------------------------------------------------------------------------------------------------#
    # Load configuration values from the specified TOML configuration file
    # Returns the configuration dictionary
    #---------------------------------------------------------------------------------------------------------------#
    def Load_Config( self, Config_Path ):
        try:
            with open( Config_Path, "rb" ) as Config_File:
                return tomllib.load( Config_File )

        except Exception as e:
            raise Exception(
                f"Unable to load configuration file:\n"
                f"\t{Config_Path}\n"
                f"\t{e}"
            )
            
#---------------------------------------------------------------------------------------------------------------#
# Main Processing
#---------------------------------------------------------------------------------------------------------------#
if ( __name__ == "__main__" ):
    App = Fix_Files()

    # Load directories from the config file
    for Directory in App.Config["Directories"]["Paths"]:
        App.Add_Directory( Directory )

    App.Build_File_List()
    App.Process_Files()
    App.Progress.Stop()
    App.Report()
    print()
    print()
