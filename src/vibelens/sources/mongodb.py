"""MongoDB data source."""


class MongoDBSource:
    """Query sessions from a remote MongoDB instance.

    Not yet implemented.
    """

    @property
    def source_type(self) -> str:
        return "mongodb"

    @property
    def display_name(self) -> str:
        return "MongoDB"
