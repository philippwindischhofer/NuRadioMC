from subprocess import Popen, PIPE
import os
import re
import logging
logger = logging.getLogger("utilities.version")
logging.basicConfig()


def get_git_commit_hash(path):
    gitproc = Popen(['git', 'show'], stdout = PIPE, cwd=path)
    (stdout, stderr) = gitproc.communicate()
    try:
        h = stdout.split('\n')[0].split()[1]
        check = re.compile(r"^[a-f0-9]{40}(:.+)?$", re.IGNORECASE)
        if(not check.match(h)):
            logging.error("NuRadioMC version could not be determined, returning None")
            return None
    except:
        return None
    return h

def get_NuRadioMC_commit_hash():
    """
    returns the hash of the current commit of the NuRadioMC git repository
    """
    import NuRadioMC
    path = os.path.dirname(NuRadioMC.__file__)
    return get_git_commit_hash(path)

def get_NuRadioReco_commit_hash():
    """
    returns the hash of the current commit of the NuRadioReco git repository
    """
    import NuRadioReco
    path = os.path.dirname(NuRadioReco.__file__)
    return get_git_commit_hash(path)