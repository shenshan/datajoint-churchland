import datajoint as dj
import os, re
import neo
from . import lab, equipment, reference, action
from typing import List, Tuple

schema = dj.schema(dj.config.get('database.prefix') + 'churchland_common_acquisition')

# =======
# LEVEL 0
# =======

@schema
class Task(dj.Lookup):
    definition = """
    # Experimental tasks
    task:                  varchar(32)  # task name
    task_version:          varchar(8)   # task version
    ---
    task_description = '': varchar(255) # additional task details
    """

    contents = [
        ['pacman',               '1.0',     '1-dimensional force tracking']
    ]

# =======
# LEVEL 1
# =======

@schema
class Session(dj.Manual):
    definition = """
    # Recording session
    session_date:                     date         # session date
    -> lab.Monkey
    ---
    -> lab.Rig
    -> Task
    session_problem = 0:              bool         # session problem. If True, session is excluded from analyses
    session_problem_description = '': varchar(255) # session problem description (e.g., corrupted data)
    """

    class Hardware(dj.Part):
        definition = """
        # Hardware used for the recording session
        -> master
        -> equipment.Hardware
        """

    class Notes(dj.Part):
        definition = """
        # Session notes
        -> master
        session_notes_id:   tinyint unsigned # session notes ID number
        ---
        session_notes = '': varchar(4095)    # session notes text
        """

        def printnotes(self):
            """Fetch and print notes."""

            for key in self:
                print((self & key).fetch1('session_notes'))

    class User(dj.Part):
        definition = """
        # Session personnel
        -> master
        -> lab.User
        """

    class Software(dj.Part):
        definition = """
        # Software used for the recording session
        -> master
        -> equipment.Software
        """


# =======
# LEVEL 2
# =======

@schema
class BehaviorRecording(dj.Manual):
    definition = """
    # Behavior recording
    -> Session
    ---
    behavior_recording_sample_rate = 1e3: smallint unsigned # behavior sample rate (Hz)
    behavior_recording_path:              varchar(1012)     # path to behavior file directory
    """

    class File(dj.Part):
        definition = """
        # Behavior recording file
        -> master
        behavior_file_id:        smallint unsigned # behavior recording file ID number
        ---
        behavior_file_path:      varchar(255)      # behavior recording file path (relative to behavior recording directory)
        behavior_file_name:      varchar(255)      # behavior recording file name
        behavior_file_extension: varchar(255)      # behavior recording file extension
        """

        def proj_file_path(self):
            """Project full file path into table."""

            return (self * BehaviorRecording).proj(
                behavior_file_path='CONCAT(behavior_recording_path, behavior_file_path, behavior_file_name, ".", behavior_file_extension)'
            )


@schema
class EphysRecording(dj.Manual):
    definition = """
    # Electrophysiological recording
    -> Session
    ---
    ephys_recording_sample_rate: smallint unsigned # ephys sample rate (Hz)
    ephys_recording_duration:    double            # ephys recording duration (s)
    ephys_recording_path:        varchar(1012)     # path to ephys file directory
    """

    class File(dj.Part):
        definition = """
        # Ephys recording file
        -> master
        ephys_file_id:        smallint unsigned # ephys recording file ID number
        ---
        ephys_file_path:      varchar(255)      # ephys recording file path (relative to ephys recording directory)
        ephys_file_name:      varchar(255)      # ephys recording file name
        ephys_file_extension: varchar(255)      # ephys recording file extension
        """

        def load(self):
            """Loads an ephys file."""

            assert len(self) == 1, 'Specify one recording file'

            # fetch full file path
            ephys_file_path = self.proj_file_path().fetch1('ephys_file_path')

            # ensure local file path
            ephys_file_path = reference.EngramTier.ensure_local(ephys_file_path)

            # load file based on file extension
            ephys_file_extension = self.fetch1('ephys_file_extension')

            if re.match('ns\d$', ephys_file_extension):

                reader = neo.rawio.BlackrockRawIO(ephys_file_path)
                reader.parse_header()

                return reader

            else:
                print('File type {} unrecognized'.format(ephys_file_extension))
                return None

        def proj_file_path(self):
            """Project full file path into table."""

            return (self * EphysRecording).proj(
                ephys_file_path='CONCAT(ephys_recording_path, ephys_file_path, ephys_file_name, ".", ephys_file_extension)'
            )


    class Channel(dj.Part):
        definition = """
        # Ephys recording file channel
        -> master.File
        ephys_channel_idx:       smallint unsigned                    # channel index in data array
        ---
        ephys_channel_id = null: smallint unsigned                    # channel ID number used by Blackrock system
        ephys_channel_type:      enum('brain', 'emg', 'sync', 'stim') # channel data type
        """


@schema
class ProbeInsertion(dj.Manual):
    definition = """
    -> Session
    probe_insertion_id:    tinyint unsigned
    """

    class File(dj.Manual):
        definition = """
        -> master
        EphysRecording.File
        """


@schema
class InsertionLocation(dj.Manual):
    definition = """
    # Brain Location of a given probe insertion.
    -> ProbeInsertion
    ---
    skull_reference: enum('lambda', 'bregma')
    ap_location: decimal(6, 2) # (um) anterior-posterior; ref is 0; more anterior is more positive
    ml_location: decimal(6, 2) # (um) medial axis; ref is 0 ; more right is more positive
    depth:       decimal(6, 2) # (um) manipulator depth relative to surface of the brain (0); more ventral is more negative
    theta=null:  decimal(5, 2) # (deg) - elevation - rotation about the ml-axis [0, 180] - w.r.t the z+ axis
    phi=null:    decimal(5, 2) # (deg) - azimuth - rotation about the dv-axis [0, 360] - w.r.t the x+ axis
    beta=null:   decimal(5, 2) # (deg) rotation about the shank of the probe [-180, 180] - clockwise is increasing in degree - 0 is the probe-front facing anterior
    """


@schema
class EphysStimulation(dj.Manual):
    definition = """
    # Electrophysiological stimulation
    -> Session
    ephys_stimulation_probe_id: tinyint unsigned  # ephys stimulation probe ID number
    ---
    -> equipment.ElectrodeArray
    probe_depth = null:         decimal(5,3)      # depth of neural probe tip relative to cortical surface (mm)
    """


# =======
# LEVEL 3
# =======

@schema
class BrainChannelGroup(dj.Manual):
    definition = """
    -> EphysRecording.File
    -> reference.BrainRegion
    brain_channel_group_id:         tinyint unsigned      # brain channel group ID number
    ---
    -> equipment.ElectrodeArray
    -> [nullable] action.BurrHole
    brain_hemisphere:               enum('left', 'right') # brain hemisphere
    brain_channel_group_notes = '': varchar(4095)         # brain channel group notes
    probe_depth = null:             decimal(5,3)          # depth of neural probe tip relative to cortical surface (mm)
    -> [nullable] equipment.ElectrodeArrayConfig
    """

    class Channel(dj.Part):
        definition = """
        # Channel number in recording file
        -> master
        -> EphysRecording.Channel
        ---
        brain_channel_idx: smallint unsigned # brain channel index
        """


@schema
class EmgChannelGroup(dj.Manual):
    definition = """
    -> EphysRecording.File
    -> reference.Muscle
    emg_channel_group_id:         tinyint unsigned # emg channel group ID number
    ---
    -> equipment.ElectrodeArray
    emg_channel_group_notes = '': varchar(4095)    # emg channel group notes
    -> [nullable] equipment.ElectrodeArrayConfig
    """

    class Channel(dj.Part):
        definition = """
        # Channel number in recording file
        -> master
        -> EphysRecording.Channel
        ---
        emg_channel_idx: smallint unsigned # EMG channel index
        """
