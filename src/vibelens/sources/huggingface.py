"""HuggingFace dataclaw data source."""


class HuggingFaceSource:
    """Pull sessions from HuggingFace dataclaw datasets.

    Not yet implemented.
    """

    @property
    def source_type(self) -> str:
        return "huggingface"

    @property
    def display_name(self) -> str:
        return "HuggingFace"
