def calculate_gpa(grades_with_credits):
    """
    Calculate weighted GPA.
    grades_with_credits: iterable of (total_score, credits) tuples.
    Returns float or None if no credits.
    """
    total_weighted = 0
    total_credits = 0
    for total, credits in grades_with_credits:
        if total is not None and credits and credits > 0:
            total_weighted += total * credits
            total_credits += credits
    if total_credits == 0:
        return None
    return round(total_weighted / total_credits, 2)
