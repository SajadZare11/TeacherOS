from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from config import missing_settings
from prompt_loader import validate_prompt_files


def package_version(name: str) -> str:
    try:
        return version(name)
    except PackageNotFoundError:
        return "NOT INSTALLED"


def main() -> None:
    print("TeacherOS project check\n")
    packages = {
        "python-telegram-bot": package_version("python-telegram-bot"),
        "openai": package_version("openai"),
        "python-dotenv": package_version("python-dotenv"),
    }

    for name, installed_version in packages.items():
        print(f"{name}: {installed_version}")
    print()

    errors: list[str] = []
    for name, installed_version in packages.items():
        if installed_version == "NOT INSTALLED":
            errors.append(
                f"Python package not installed: {name}. "
                "Run: python -m pip install -r requirements.txt"
            )

    missing = missing_settings()
    if missing:
        errors.append("Missing .env values: " + ", ".join(missing))
    else:
        print("✅ .env settings found")

    try:
        validate_prompt_files()
        print("✅ Required prompt files found")
    except Exception as exc:
        errors.append(str(exc))

    if errors:
        print("\n❌ Problems found:")
        for error in errors:
            print(f"- {error}")
        raise SystemExit(1)

    print("\n✅ Basic project check passed")


if __name__ == "__main__":
    main()

