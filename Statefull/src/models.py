"""
Data models and state definitions for the joke generation agent.
"""

from typing import TypedDict, Optional


class JokeState(TypedDict):
    """
    State definition for the joke generation workflow.
    
    Attributes:
        topic (str): The topic for which to generate a joke
        joke (str): The generated joke content
        explanation (str): The explanation of the joke
        status (str): Current status of the workflow
    """
    topic: str
    joke: Optional[str]
    explanation: Optional[str]
    status: str  # "started", "joke_generated", "completed"
