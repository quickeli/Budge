def to_cents(amount_str: str) -> int:
    """
    Converts a string amount to cents.
    - Removes commas and dollar signs.
    - Handles negative amounts.
    - Expects two decimal places.
    """
    if not amount_str:
        return 0
    # remove commas and dollar signs
    amount_str = amount_str.replace(",", "").replace("$", "")
    # handle negative amounts
    multiplier = -1 if amount_str.startswith("-") else 1
    if multiplier == -1:
        amount_str = amount_str[1:]
    # expect two decimal places
    if "." not in amount_str:
        return int(amount_str) * 100 * multiplier
    dollars, cents = amount_str.split(".")
    if len(cents) != 2:
        raise ValueError("Amount must have two decimal places")
    return (int(dollars) * 100 + int(cents)) * multiplier


def cents_to_str(cents: int) -> str:
    """
    Converts cents to a string amount.
    """
    if cents is None:
        return ""
    return f"{cents / 100:.2f}"
