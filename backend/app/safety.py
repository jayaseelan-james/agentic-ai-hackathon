"""Conservative reported-symptom checks; not a roadworthiness assessment."""
import re

SAFETY = 'If you are driving, stop safely as soon as possible. Do not continue driving. Arrange qualified roadside or workshop assistance.'
RULES = [
    r'(?:brake|braking|pedal).{0,35}(?:soft|spongy|floor|fail|not work|ineffective)',
    r'(?:soft|spongy).{0,20}(?:brake|pedal)',
    r'red.{0,20}brake.{0,25}(?:on|stay|persist|warning|light)',
    r'(?:brake warning|brake light).{0,30}(?:red|stay|persist)',
    r'(?:fuel|petrol|gasoline).{0,20}(?:leak|smell)',
    r'(?:smoke|fire|flames|overheat|steam from|flat tire|flat tyre)',
    r'(?:steering).{0,25}(?:fail|lock|not work|lost)',
]


def critical(text: str) -> bool:
    # Clause splitting prevents negation in one sentence suppressing another concern.
    for clause in re.split(r'[.!?;\n]|\bbut\b', text.lower()):
        if re.search(r'\b(no|not|without|never)\s+(?:any\s+)?(?:smoke|fire|flames|fuel leak|flat tire|flat tyre|overheating)\b', clause):
            clause = re.sub(r'\b(no|not|without|never)\s+(?:any\s+)?(?:smoke|fire|flames|fuel leak|flat tire|flat tyre|overheating)\b', '', clause)
        if any(re.search(rule, clause) for rule in RULES):
            return True
    return False


def unsafe_answer(text: str) -> bool:
    # Reject affirmative assurances, not questions or disclaimers mentioning safety.
    text = re.sub(r"\b(?:cannot|can't|unable|whether|if|not)\b[^.!?;\n]{0,100}\b(?:safe to drive|roadworthy)\b", '', text.lower())
    return bool(re.search(r"\b(?:(?:it is|it's|car is|vehicle is|you are|you're|should be|appears)\s+(?:now |generally |probably |likely )?(?:safe to drive|roadworthy)|you can (?:safely )?drive|(?:first|then|next|step \d+)\b.{0,35}\bbleed (?:the |your )?brakes|bypass (?:the )?(?:warning|interlock))\b", text))
