
#---------------------------------------------------------------------------------------------------------------#
# Load Modules
# python -m pip install --upgrade module
#---------------------------------------------------------------------------------------------------------------#

# rich_progress.py
from rich.progress import (
    Progress, 
    ProgressColumn,
    BarColumn, 
    TextColumn, 
    TimeRemainingColumn,
    TimeElapsedColumn,
    SpinnerColumn
)

from rich.panel import Panel
from rich.live import Live
from rich import print

from rich import traceback
traceback.install()                                                  # Ensures rich tracebacks is used for uncaught exceptions

from threading import Lock
import threading
import time                                                      # Handle time-related functions (sleep, time tracking)

# Table
from rich.console import Console
from rich.table import Table
from rich.color import Color, ANSI_COLOR_NAMES                          # Import valid color names for validation

#---------------------------------------------------------------------------------------------------------------#
# Class: DynamicColorBarColumn
# A custom progress bar column that dynamically changes color based on completion percentage.
#---------------------------------------------------------------------------------------------------------------#
class DynamicColorBarColumn(ProgressColumn):
    def render(self, Task ) -> str:
        Percent = Task.completed / Task.total if Task.total else 0
        Bar_Width = 50
        Completed_Width = int(Percent * Bar_Width)
        Remaining_Width = Bar_Width - Completed_Width
        color = self.Calculate_Rainbow_Color(Percent)
        return f"[{color}]{ '-' * Completed_Width }{' ' * Remaining_Width}[/{color}]"

    def Calculate_Rainbow_Color(self, Percent):
        # Rainbow color calculation
        r = int(255 * (1 - Percent))
        g = int(255 * Percent)
        b = 0
        return f"#{r:02x}{g:02x}{b:02x}"

#---------------------------------------------------------------------------------------------------------------#
# Class: CustomStateColumn
# Display a column with State information
#---------------------------------------------------------------------------------------------------------------#
class CustomStateColumn(ProgressColumn):
    def render( self, task ) -> str:
        state = task.fields.get( "state", "" )
        return f"[{state}]"

#---------------------------------------------------------------------------------------------------------------#
# Class: Rich_Progress
# A class to manage rich progress bars for total and detailed progress tracking.
#---------------------------------------------------------------------------------------------------------------#
class Rich_Progress:
    Live = None
    Length_Description = 40  # Default length for descriptions in the first column

    #---------------------------------------------------------------------------------------------------------------#
    # Class Initialization
    #---------------------------------------------------------------------------------------------------------------#
    def __init__(self):
        self.Console = Console()
        #self.Console = Console( 
        #    theme=Theme( 
        #        { "bar.complete": "cyan",
        #          "bar.finished": "rgb(114,156,31)",
        #          "bar.pulse": "cyan",
        #          "progress.percentage": "italic bright_cyan"
        #        }
        #    ) 
        #)
        self.Progress_Overall = Progress(
            TextColumn("[progress.description]{task.description}"),
            SpinnerColumn(),
            BarColumn(),
            #DynamicColorBarColumn(),
            "[progress.percentage]{task.percentage:>3.1f}%",
            TimeElapsedColumn(),
            console=self.Console,
            transient=True,
            expand=True
        )

        self.Progress_Detailed = Progress(
            TextColumn( "[progress.description]{task.description}"),
            #TextColumn(lambda task: f"{task.description[:40]}"),
            SpinnerColumn(),
            BarColumn(),
            #DynamicColorBarColumn(),
            CustomStateColumn(),
            "[progress.percentage]{task.percentage:>3.1f}%",
            TimeElapsedColumn(),
            console=self.Console,
            transient=True,
            expand=True
        )

        self.Progress_Sleep = Progress(
            TextColumn( "[progress.description]{task.description:<40}" ),
            SpinnerColumn(),
            BarColumn(),
            #DynamicColorBarColumn(),
            "[progress.percentage]{task.percentage:>3.1f}%",
            TimeElapsedColumn(),
            console=self.Console,                    #,
            transient=True,  # Mark transient to allow reusing the row
            expand=True
        )


        self.Progress_Table = Table.grid()
        self.Progress_Table.min_width = 120
        
        self.Task_Lock = Lock()
        Text_Total = f"[blue]Total Progress"
        if ( len( Text_Total ) > self.Length_Description ):
            Text_Total = Text_Total[:self.Length_Description]  # Truncate if too long
        else:
            Text_Total = Text_Total.ljust( self.Length_Description )  # Pad if too short

        self.Total_Task_ID = self.Progress_Overall.add_task( Text_Total, total=100 )

    #---------------------------------------------------------------------------------------------------------------#
    # Function: Start
    # Start the rich progress context manager.
    #---------------------------------------------------------------------------------------------------------------#
    def Start( self, Text_Overall="Overall Progress", Text_Detailed="Detailed Progress" ):

        self.Progress_Table.add_row( 
            Panel.fit( self.Progress_Overall, title= Text_Overall, padding= ( 1, 2 ) )
        )
        self.Progress_Table.add_row( 
            Panel.fit( self.Progress_Detailed, title= Text_Detailed, padding= ( 1, 2 ) )
        )
        self.Progress_Table.add_row( 
            Panel.fit( self.Progress_Sleep, title= "", padding= ( 0, 0 ), border_style = "black on black" )
        )
        self.Live = Live ( self.Progress_Table, console=self.Console )
        self.Live.start()

    #---------------------------------------------------------------------------------------------------------------#
    # Function: Stop
    # Stop the rich progress context manager.
    #---------------------------------------------------------------------------------------------------------------#
    def Stop(self):
        self.Live.stop()

    #---------------------------------------------------------------------------------------------------------------#
    # Function: Add_Task
    # Add a new detailed task.
    # Returns the task ID.
    #---------------------------------------------------------------------------------------------------------------#
    def Add_Task(self, Description, Total):
        try:
            #print( f"Add_Task: {description}" )
            with self.Task_Lock:
                if ( Description ):
                    if ( len( Description ) > self.Length_Description ):
                        Description = Description[:self.Length_Description]  # Truncate if too long
                    else:
                        Description = Description.ljust( self.Length_Description )  # Pad if too short

                Task_ID = self.Progress_Detailed.add_task( Description, total=Total, visible=False )
                #self.Tasks[Task_ID] = {"total": Total, "completed": 0, "visible": True, "description": Description}
                self.Update_Total_Progress()
                return Task_ID
        except Exception as e:
            print( f"An Error occurred in Add_Task():\n{e}" )


    #---------------------------------------------------------------------------------------------------------------#
    # Function: Update_Task
    # Update the progress of a detailed task.
    #---------------------------------------------------------------------------------------------------------------#
    def Update_Task(self, Task_ID, Advance=None, Total=None, Description=None, State=None, Visible=None ):
        try:
            with self.Task_Lock:
                if ( Description ):
                    if ( len( Description ) > self.Length_Description ):
                        Description = Description[:self.Length_Description]  # Truncate if too long
                    else:
                        Description = Description.ljust( self.Length_Description )  # Pad if too short

                if ( Advance is not None ):
                    #print( f"Updating {Task_ID} Advance" )
                    self.Progress_Detailed.update(Task_ID, advance=Advance )
                    #self.Tasks[Task_ID]["completed"] += Advance
                if ( Total is not None ):
                    #print( f"Updating {Task_ID} Total" )
                    self.Progress_Detailed.update(Task_ID, total=Total )
                    #self.Tasks[Task_ID]["total"] = Total
                if ( Description is not None ):
                    #print( f"Updating {Task_ID} Description" )
                    self.Progress_Detailed.update(Task_ID, description=Description )
                    #self.Tasks[Task_ID]["description"] = Description
                if ( State is not None ):
                    self.Progress_Detailed.update(Task_ID, state=State )
                if ( Visible is not None ):
                    self.Progress_Detailed.update(Task_ID, visible=Visible )
                self.Update_Total_Progress()
        except Exception as e:
            print( f"An Error occurred in Update_Task():\n{e}" )

    #---------------------------------------------------------------------------------------------------------------#
    # Function: Validate_Task
    # Displays current Task settings - used in debugging
    #---------------------------------------------------------------------------------------------------------------#
    def Validate_Task( self, Task_ID ):
        try:
            with self.Task_Lock:
                Task = self.Progress_Detailed.tasks[Task_ID]

                #Task = self.Tasks.get( Task_ID )
                if Task is None:
                    print(f"Task {Task_ID} not found.")
                else:
                    print( f"Task ID: {Task_ID}" )
                    print( f"\tDescription: {Task.description}" )
                    print( f"\tTotal: {Task.total}" )
                    print( f"\tCompleted: {Task.completed}" )
                    print( f"\tRemaining: {Task.remaining}" )
                    print( f"\tFinished: {Task.finished}" )
                    print( f"\tPercent: {Task.percentage}" )
        except Exception as e:
            print( f"An Error occurred in Validate_Task():\n{e}" )


    #---------------------------------------------------------------------------------------------------------------#
    # Function: Update_Total_Progress
    # Update the overall total progress based on detailed tasks.
    #---------------------------------------------------------------------------------------------------------------#
    def Update_Total_Progress(self):
        try:
            # Calculate total completed and total tasks, ensuring no task exceeds 100% completed
            Total_Completed = sum( min( task.completed, task.total) for task in self.Progress_Detailed.tasks )
            Total = sum( task.total for task in self.Progress_Detailed.tasks )

            if ( Total > 0 ):
                # Calculate overall progress as a percentage
                Overall_Progress = Total_Completed / Total * 100

                # If all tasks are 100% completed, set overall progress explicitly to 100%
                if ( all(task.completed == task.total for task in self.Progress_Detailed.tasks) ):
                    Overall_Progress = 100

                # Update the overall progress bar with the calculated or adjusted progress
                self.Progress_Overall.update(self.Total_Task_ID, completed=Overall_Progress)

        except Exception as e:
            print(f"An Error occurred in Update_Total_Progress():\n{e}")

    #---------------------------------------------------------------------------------------------------------------#
    # Function: Hide_Task
    # Hide a detailed task from the display but keep its progress data.
    #---------------------------------------------------------------------------------------------------------------#
    def Hide_Task( self, Task_ID ):
        with self.Task_Lock:
            #if Task_ID in self.Tasks:
            self.Progress_Detailed.update( Task_ID, visible=False )
            #    self.Tasks[Task_ID]["visible"] = False
            self.Update_Total_Progress()

    #---------------------------------------------------------------------------------------------------------------#
    # Function: Hide_Task
    # Hide a detailed task from the display but keep its progress data.
    #---------------------------------------------------------------------------------------------------------------#
    def Complete_Task( self, Task_ID ):
        """
        Mark a task as complete by setting its completed value equal to its total
        and then hiding it from the detailed progress view.
        """
        with self.Task_Lock:
            task = self.Progress_Detailed.tasks[Task_ID]

            if ( task ):
                # Ensure the task is 100% complete
                self.Progress_Detailed.update( Task_ID, completed=task.total )
            else:
                # Optionally log or handle a case where the task ID is not found
                print(f"Task {Task_ID} not found.")
            self.Update_Total_Progress()

    #---------------------------------------------------------------------------------------------------------------#
    # Function: Update_Total
    # Increase the total of a specified task.
    #---------------------------------------------------------------------------------------------------------------#
    def Update_Total( self, Task_ID, Addition ):
        try:
            with self.Task_Lock:
                Task = self.Progress_Detailed.tasks[Task_ID]

                #Task = self.Tasks.get( Task_ID )
                if Task is None:
                    print(f"Task {Task_ID} not found.")
                else:
                    New_Total = Task.total + Addition
                    self.Progress_Detailed.update( Task_ID, total=New_Total )

        except Exception as e:
            print( f"An Error occurred in Validate_Task():\n{e}" )

    #---------------------------------------------------------------------------------------------------------------#
    # Function: Sleep
    # Sleep for a time period, while providing a status
    #---------------------------------------------------------------------------------------------------------------#
    def Sleep( self, Sleep_Seconds ):
        try:
            #print( f"Getting sleepy" )
            with self.Task_Lock:
                #self.Progress_Table.add_row( 
                #    Panel.fit( self.Progress_Sleep, title= "Sleeping", padding= ( 0, 0 ) )
                #)

                #Progress_Sleep = Progress(
                #    TextColumn( "[progress.description]{task.description:<40}" ),
                #    SpinnerColumn(),
                #    BarColumn(),
                #    #DynamicColorBarColumn(),
                #    "[progress.percentage]{task.percentage:>3.1f}%",
                #    TimeElapsedColumn(),
                #    console=self.Console,                    #,
                #    transient=True  # Mark transient to allow reusing the row
                #)
                #self.Progress_Table.add_row( 
                #    Panel.fit( Progress_Sleep, title= "", padding= ( 0, 1 ), border_style = "black on black" )
                #)

                #Task_ID = self.Progress_Detailed.add_task( "Sleeping", total=Seconds )
                Minutes, Seconds = divmod( Sleep_Seconds, 60 )
                Formatted_Time = f"Sleeping {int(Minutes)} minutes, {int(Seconds)} seconds"
                #ID_Sleep = self.Add_Sleep( f"{Formatted_Time}", Sleep_Seconds )
                ID_Sleep = self.Progress_Sleep.add_task( f"{Formatted_Time}", total=Sleep_Seconds )
                #print( f"Sleeping: {Seconds} seconds" )
                #ID_Sleep = self.Progress_Overall.add_task( ID_Sleep, description=f"Sleeping...", total=Seconds )
                for Elapsed_Seconds in range( 1, Sleep_Seconds ):
                    time.sleep(1)
                    Remaining_Seconds = Sleep_Seconds - Elapsed_Seconds
                    Minutes, Seconds = divmod( Remaining_Seconds, 60 )
                    Formatted_Time = f"Sleeping {int(Minutes)} minutes, {int(Seconds)} seconds"
                    self.Progress_Sleep.update( ID_Sleep, description=f"{Formatted_Time}", advance=1 )

                
                #self.Progress_Overall.update( ID_Sleep, visible=False )
                self.Progress_Sleep.update( ID_Sleep, visible=False )
                # After sleep, remove the task from display
                #self.Progress_Sleep.remove_task( ID_Sleep )

                # Stop and remove the Progress_Sleep instance after sleep ends
                #self.Progress_Sleep.stop()  # Stop the progress display

                #Progress_Sleep.disable
                

        except Exception as e:
            print( f"An Error occurred in Sleep():\n{e}" )


    #---------------------------------------------------------------------------------------------------------------#
    # Function: Sleep
    # Sleep for a time period, while providing a status
    #---------------------------------------------------------------------------------------------------------------#
    def Display_Colors( self ):
        try:
            # Create a Console object to print to the terminal
            console = Console()

            # Create a table with specified column headers
            Color_Table = Table( title=f"Available Colors" )
            Color_Table.add_column("Sample", justify="left", style="cyan", no_wrap=True)
            Color_Table.add_column("Name", justify="center", style="white", no_wrap=True)
            Color_Table.add_column("Example Text", justify="center", style="cyan", no_wrap=True)

            # Loop over each color in ANSI_COLOR_NAMES
            for Color_Name in ANSI_COLOR_NAMES.keys():
                # Create a sample text that uses the color
                Sample_Color = f"[{Color_Name}]-----------------------[/{Color_Name}]"
                Sample_Color = f"[{Color_Name}]███████████████████████[/{Color_Name}]"
                Example_Text = f"[{Color_Name}]Example of the color[/{Color_Name}]"
                # Add the row with the color preview and name
                color = Color.parse( Color_Name )
                ANSI = f"{color.get_ansi_codes()}"
                RGB = f"{color.get_truecolor()}"

                # Add the row with the color preview, name, and RGB values
                Color_Table.add_row( Sample_Color, Color_Name, Example_Text )

            # Print the table to the console
            console.print( Color_Table )

        except Exception as e:
            print( f"An Error occurred in Display_Colors():\n{e}" )

    #---------------------------------------------------------------------------------------------------------------#
    # Display error info using Rich's Traceback
    #---------------------------------------------------------------------------------------------------------------#
    def Traceback( self, Exception ):
        self.Console.print(
            Traceback.from_exception(
                type( Exception ),
                Exception,
                Exception.__traceback__,
                show_locals=True  # Show local variables in the traceback
            )
            
        )

#---------------------------------------------------------------------------------------------------------------#
# Main functionality
#---------------------------------------------------------------------------------------------------------------#
if __name__ == "__main__":
    progress = Rich_Progress()

    progress.Display_Colors()

    def task_worker( task_id, progress, steps=10 ):
        progress.Update_Task( task_id, Visible = True )
        for _ in range( steps ):
            progress.Update_Task( task_id, Advance = 10 )
            time.sleep( 0.5 )
        progress.Hide_Task( task_id )

    progress.Start()

    for i in range(5):
        task_id = progress.Add_Task( f"Task {i+1}", Total=100 )
        threading.Thread( target=task_worker, args=( task_id, progress ) ).start()

    time.sleep(6)  # Simulate doing other work

    