import pandas as pd
from django_pandas.io import read_frame

class ToDataFrameCmd:
    """ToDataFrame command for converting input data to pandas DataFrame."""
    name = "to_dataframe"

    def add_arguments(self, p):
        pass  # No arguments needed for this command

    def run_qs(self, qs, args, ctx):
        """Return queryset as pandas DataFrame."""
        return read_frame(qs)

    def run_df(self, df, args, ctx):
        """Return DataFrame as is."""
        return df

    def run_records(self, rows, args, ctx):
        """Return records (list of dicts) as pandas DataFrame."""
        return pd.DataFrame(rows)
