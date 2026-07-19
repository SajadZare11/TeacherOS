# prompt_loader.py

def load_prompt(file_path: str) -> str:
    """
    Reads a prompt from a text file and returns it as a string.
    """

    with open(file_path, "r", encoding="utf-8") as file:
        prompt = file.read()

    return prompt
