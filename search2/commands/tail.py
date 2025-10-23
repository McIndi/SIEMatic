class TailCmd:
    """Tail command for getting the last N rows.
    Examples:
        tail --n=10
    """
    name = "tail"

    def add_arguments(self, p):
        p.add_argument(
            "--n",
            type=int,
            default=10,
            help="Number of rows to return (default: 10)",
        )

    def run_none(self, data, args, ctx):
        raise NotImplementedError("tail command requires input data")

    def run_qs(self, qs, args, ctx):
        """Get last N rows using Django ORM."""
        # For querysets, tail is inefficient - convert to DataFrame
        return qs[-args.n:] if len(qs) >= args.n else qs

    def run_df(self, df, args, ctx):
        """Get last N rows using pandas tail."""
        return df.tail(args.n)

    def run_records(self, rows, args, ctx):
        """Get last N rows using Python slicing."""
        return rows[-args.n:] if len(rows) >= args.n else rows