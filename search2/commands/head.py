class HeadCmd:
    """Head command for getting the first N rows.
    Examples:
        head --n=10
    """
    name = "head"

    def add_arguments(self, p):
        p.add_argument(
            "--n",
            type=int,
            default=10,
            help="Number of rows to return (default: 10)",
        )

    def run_none(self, data, args, ctx):
        raise NotImplementedError("head command requires input data")

    def run_qs(self, qs, args, ctx):
        """Get first N rows using Django ORM slicing."""
        return qs[:args.n]

    def run_df(self, df, args, ctx):
        """Get first N rows using pandas head."""
        return df.head(args.n)

    def run_records(self, rows, args, ctx):
        """Get first N rows using Python slicing."""
        return rows[:args.n]