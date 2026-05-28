def get_discipline_key(discipline_str: str) -> str | None:
    """
    Maps a free-text discipline string (e.g. '6th Grade Math') to 
    an ERIC discipline key (e.g. 'ms_math').
    """
    d = discipline_str.lower()
    
    # Lower School
    if "elementary" in d or "lower school" in d or "k-5" in d:
        if "math" in d: return "ls_math"
        if "science" in d: return "ls_science"
        if "art" in d: return "ls_arts"
        if "music" in d: return "ls_arts"
        if "pe" in d or "phys" in d: return "ls_pe"
        if "steam" in d: return "ls_steam"
        if "library" in d: return "ls_library"
        if "support" in d or "learning" in d: return "ls_learning_support"
        return "ls_homeroom"

    # Middle School
    if "middle" in d or "6-8" in d or "6th" in d or "7th" in d or "8th" in d:
        if "english" in d or "ela" in d or "reading" in d: return "ms_english"
        if "math" in d: return "ms_math"
        if "science" in d: return "ms_science"
        if "history" in d or "social studies" in d: return "ms_history"
        if "world language" in d or "spanish" in d or "french" in d: return "ms_world_language"
        if "pe" in d or "phys" in d: return "ms_pe"
        if "steam" in d or "robotics" in d: return "ms_steam"
        if "art" in d: return "ms_arts"
        if "debate" in d: return "ms_debate"

    # Upper School / Default
    if "english" in d: return "us_english"
    if "math" in d or "calc" in d or "algebra" in d: return "us_math"
    if "science" in d or "bio" in d or "chem" in d or "phys" in d: return "us_science"
    if "history" in d or "social studies" in d or "civics" in d: return "us_history"
    if "world language" in d or "spanish" in d or "french" in d or "latin" in d: return "us_world_language"
    if "computer" in d or "cs" in d or "programming" in d: return "us_cs"
    if "art" in d: return "us_arts"
    if "economics" in d or "psych" in d or "social science" in d: return "us_social_science"
    if "support" in d or "learning" in d: return "us_learning_support"
    
    if "global" in d or "leadership" in d: return "global_leadership"
    if "counseling" in d or "sel" in d: return "counseling"

    return None


def get_search_keyword_prompt(profile):
    """
    Generates a prompt to extract search keywords from a teacher profile.
    """
    return f"""Based on the teacher profile below, generate a list of 5-8 specific search keywords or short phrases.
These keywords will be used to search a database of educational research articles.
Focus on the discipline, current module, and specific tailoring goals.

### Teacher Profile:
- **Discipline:** {profile.get('discipline', 'General Education')}
- **Grade Band:** {profile.get('grade_band', 'N/A')}
- **Current Module/Unit:** {profile.get('current_module', 'N/A')}
- **Tailoring Query:** {profile.get('tailoring_query', 'N/A')}

### Instructions:
- Return ONLY a comma-separated list of keywords.
- Do not include "Pace Academy" as a keyword.
- Prioritize technical pedagogical terms (e.g., "scaffolded writing", "active retrieval").
- Include both subject-matter keywords and teaching-method keywords.

### Output:
Keyword1, Keyword2, Keyword3..."""


def get_system_prompt(profile):
    """
    Generates a personalized system prompt with a rigorous pedagogical heuristic.
    """
    
    # Persona Logic
    exp = int(profile.get('years_experience', 5))
    if exp <= 3:
        persona = "Novice Teacher"
        emphasis = "classroom management, clear mechanics, and simple execution steps."
    elif 4 <= exp <= 9:
        persona = "Developing Professional"
        emphasis = "differentiation and student engagement strategies."
    else:
        persona = "Veteran Educator"
        emphasis = "advanced differentiation, avoiding curriculum fatigue, and leadership."

    # Rigorous Pedagogical Heuristic
    heuristic = """
1. **Evidence-Based:** The article must be grounded in empirical research, cognitive science, or established pedagogical frameworks. Reject "fluff" or opinion-only pieces.
2. **Actionability:** The research must translate into a technique that can be implemented with minimal prep. If it requires a full curriculum overhaul, reject it for this digest.
3. **Grade-Appropriate:** The strategy must be developmentally suitable for the teacher's Grade Band.
4. **Subject-Specific:** Prioritize articles that directly impact the teacher's Discipline or offer a highly transferable cross-curricular strategy.
5. **Freshness:** Favor recent insights (last 3-5 years) unless the concept is a foundational "classic" of pedagogy.
    """

    mission = (
        "Pace Academy develops curious, ethical, and skilled individuals who are prepared to "
        "make a positive difference in the world through academic excellence, character "
        "development, and a commitment to community."
    )

    prompt = f"""You are a trusted mentor helping {profile.get('first_name', 'a teacher')} find research that's actually useful in their classroom.
Translate the article below into practical, direct advice — not textbook language.

### About this teacher:
- Discipline: {profile.get('discipline', 'General Education')}
- Grade Band: {profile.get('grade_band', 'N/A')}
- Current Unit: {profile.get('current_module', 'N/A')}
- Experience: {persona} — focus on {emphasis}
- Looking for: {profile.get('tailoring_query', 'N/A')}

### Evaluation criteria:
{heuristic}

### Task:
Evaluate the article. If it passes, return a JSON object with:

1. "decision": "Yes"
2. "summary": 2 sentences. Plain English. What's the key idea and why does it matter?
3. "action_steps": A list of exactly 3 classroom tips. Write like a colleague giving quick, direct advice — start each with a verb, keep each to 1-2 sentences, no numbers or bullets in the text, no jargon.
4. "mission_alignment": One natural sentence connecting this to Pace students. Do NOT quote or echo the mission statement — just say it plainly.

If it fails, return:
{{"decision": "No", "reason": "Brief explanation of which criterion it failed."}}

Return ONLY a valid JSON object. No preamble or postscript."""

    return prompt
