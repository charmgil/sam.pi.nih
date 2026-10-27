"""samkit: deterministic GWAS + PRS core driven by the SAM pi harness.

Every step reads only from the input/resource directories given at run time
and writes only below the output directory (default: ./output of the working
directory). Steps print one JSON summary to stdout; progress goes to stderr.
"""

__version__ = "0.1.0"
