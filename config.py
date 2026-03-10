import os
import sys
import glob
from dotenv import load_dotenv
from aita_core import CourseConfig

load_dotenv()

BASE_DIR = os.path.dirname(__file__)
_explicit_secret = os.getenv("GOOGLE_CLIENT_SECRET_FILE", "")
if _explicit_secret:
    _client_secret_matches = [os.path.join(BASE_DIR, _explicit_secret)] if os.path.exists(os.path.join(BASE_DIR, _explicit_secret)) else []
else:
    _client_secret_matches = glob.glob(os.path.join(BASE_DIR, "client_secret*.json"))

# Google Auth requires: client_secret file + GOOGLE_COOKIE_KEY + GOOGLE_REDIRECT_URI
_google_cookie_key = os.getenv("GOOGLE_COOKIE_KEY")
_google_redirect_uri = os.getenv("GOOGLE_REDIRECT_URI")
if _client_secret_matches and _google_cookie_key and _google_redirect_uri:
    _google_client_secret = _client_secret_matches[0]
else:
    _google_client_secret = ""
    if _client_secret_matches:
        print("[WARN] Google OAuth: client_secret found but GOOGLE_COOKIE_KEY or "
              "GOOGLE_REDIRECT_URI not set. Falling back to student ID login.",
              file=sys.stderr)

SYSTEM_PROMPT = """\
You are an AI Teaching Assistant for CEGE 3102: Uncertainty and Decision Analysis \
at the University of Minnesota. The course covers probability and statistics \
for civil engineering students, taught by Prof. Michael Levin.

YOUR CORE PRINCIPLE: You must NEVER give direct answers to homework or exam problems. \
Instead, you should:
- Ask Socratic questions to guide students toward understanding
- Provide hints and point students to relevant concepts or course materials
- Explain underlying principles without solving the specific problem
- Encourage students to attempt the problem first and share their reasoning
- When students share their work, help them identify errors conceptually
- Use analogies and simple examples (different from homework) to build intuition

CRITICAL — CATCHING MISCONCEPTIONS:
When a student provides an example, explanation, or reasoning, you MUST carefully check \
whether it is correct before praising or accepting it. Specifically:
- Check if the example actually satisfies all assumptions/conditions of the concept \
(e.g., independence, identical trials, finite/infinite support, etc.)
- If the student's example violates an assumption you just explained, point it out \
immediately and gently — do NOT say "Great start!" and move on
- Ask the student: "Does your example satisfy all the conditions we discussed?" \
before confirming it is correct
- It is better to catch a misconception early than to let it pass uncorrected
- Remember: students learn MORE from having their mistakes caught than from being told \
they are right when they are wrong

When responding:
- If your answer draws on course materials, cite the source (e.g., "See Handout 3: Conditional Probability")
- If a question is clearly a homework problem, acknowledge it and help them understand the concept, but do NOT solve it
- Be encouraging, patient, and supportive
- Keep responses focused and concise — students want clarity, not walls of text
- If the question is not related to the course, politely redirect
- Use LaTeX for math: inline with single dollars $P(A|B)$ and display math with double dollars $$P(A|B) = \\frac{P(A \\cap B)}{P(B)}$$
- IMPORTANT: Never use \\[ \\] or \\( \\) for LaTeX. Always use $...$ for inline and $$...$$ for display equations.

You will be provided with relevant context from course materials to ground your responses.\
"""

CONFIG = CourseConfig(
    course_id="3102",
    course_name="CEGE 3102: AI Teaching Assistant",
    course_short_name="CEGE 3102 AITA",
    course_description=(
        "Welcome! This AI assistant helps you learn probability and statistics "
        "concepts for **CEGE 3102: Uncertainty and Decision Analysis**."
    ),
    system_prompt=SYSTEM_PROMPT,
    semester_start="2026-01-20",
    week_topics={
        1:  ["Fundamentals of probability"],
        2:  ["Fundamentals of probability", "Conditional probability"],
        3:  ["Conditional probability", "Combinatorics"],
        4:  ["Combinatorics", "Discrete random variables"],
        5:  ["Special discrete distributions"],
        6:  ["CDFs, expectation, and variance"],
        7:  ["Continuous random variables"],
        8:  ["Midterm 1 review", "Special continuous distributions"],
        9:  ["Special continuous distributions", "Joint distributions"],
        10: ["Joint distributions", "Central limit theorem"],
        11: ["Point estimation"],
        12: ["Midterm 2 review", "Confidence intervals"],
        13: ["Confidence intervals", "Monte Carlo simulation"],
        14: ["Hypothesis testing"],
        15: ["Linear regression"],
    },
    topic_num_to_week={
        1: 1, 2: 1, 3: 2, 4: 3, 5: 4, 6: 5, 7: 7,
        8: 9, 9: 10, 10: 11, 11: 12, 12: 13, 13: 14, 14: 15,
    },
    hw_num_to_week={
        1: 2, 2: 3, 3: 4, 4: 5, 5: 6, 6: 7,
        7: 9, 8: 10, 9: 11, 10: 12, 11: 13, 12: 14,
    },
    lab_num_to_week={
        1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6, 7: 7,
        8: 8, 9: 10, 10: 11, 11: 12, 12: 14, 13: 15,
    },
    study_guide_to_week={
        "Quiz 1 ": 3, "Quiz 2 ": 4, "Quiz 3 ": 5, "Quiz 4 ": 6,
        "Quiz 5 ": 7, "Quiz 6 ": 8, "Quiz 7 ": 9, "Quiz 8 ": 11,
        "Quiz 9 ": 12, "Quiz 10": 13, "Quiz 11": 14,
        "Midterm 1": 8, "Midterm 2": 12, "Final exam": 15,
    },
    exam_scope={
        "Midterm 1": {"week_start": 1, "week_end": 7},
        "Midterm 2": {"week_start": 8, "week_end": 11},
        "Final": {"week_start": 1, "week_end": 15},
    },
    example_prompts={
        1: [
            "What is a sample space?",
            "Can you explain the difference between a population and a sample?",
            "How do I calculate the mean and standard deviation?",
            "What topics does this course cover?",
        ],
        2: [
            "What is this week's homework?",
            "Can you explain conditional probability with an example?",
            "What is the difference between P(A and B) and P(A|B)?",
            "Help me review for Quiz 1",
        ],
        3: [
            "What is Bayes' theorem and when do I use it?",
            "How do permutations differ from combinations?",
            "Can you help me with this week's homework?",
            "What should I study for Quiz 1?",
        ],
        4: [
            "What is a random variable?",
            "Can you explain the difference between discrete and continuous RVs?",
            "Help me understand the binomial distribution",
            "What is this week's homework about?",
        ],
        5: [
            "What are the common discrete distributions?",
            "When should I use Poisson vs Binomial?",
            "Can you explain the geometric distribution?",
            "Help me with this week's homework",
        ],
        6: [
            "What is a CDF and how is it different from a PMF?",
            "How do I calculate expected value and variance?",
            "Can you explain the properties of expectation?",
            "Help me prepare for Quiz 4",
        ],
        7: [
            "What is a probability density function?",
            "How is the normal distribution defined?",
            "Can you explain how to use z-tables?",
            "Help me with this week's homework",
        ],
        8: [
            "What should I study for Midterm 1?",
            "Can you explain the exponential distribution?",
            "What are the key formulas I need to know so far?",
            "How does the uniform distribution work?",
        ],
        9: [
            "What is a joint distribution?",
            "How do I find marginal distributions from a joint PMF?",
            "What does it mean for two random variables to be independent?",
            "Help me with this week's homework",
        ],
        10: [
            "Can you explain the Central Limit Theorem?",
            "Why is the CLT important in statistics?",
            "What is a sampling distribution?",
            "Help me with this week's homework",
        ],
        11: [
            "What is point estimation?",
            "Can you explain the method of moments?",
            "What makes an estimator unbiased?",
            "Help me prepare for Quiz 8",
        ],
        12: [
            "What should I study for Midterm 2?",
            "How do I construct a confidence interval?",
            "What is the difference between a 90% and 95% confidence interval?",
            "Help me with this week's homework",
        ],
        13: [
            "What is Monte Carlo simulation?",
            "How do I interpret a confidence interval?",
            "Can you explain the margin of error?",
            "Help me with this week's homework",
        ],
        14: [
            "What is hypothesis testing?",
            "Can you explain Type I and Type II errors?",
            "What is a p-value?",
            "Help me with this week's homework",
        ],
        15: [
            "How does linear regression work?",
            "What is the least squares method?",
            "What should I study for the final exam?",
            "Can you give me a summary of all topics?",
        ],
    },
    base_dir=BASE_DIR,
    course_materials_dir=os.path.join(BASE_DIR, "course_materials"),
    faiss_db_dir=os.path.join(BASE_DIR, "faiss_db"),
    docs_dir=os.path.join(BASE_DIR, "docs"),
    backup_dir=os.path.join(BASE_DIR, "backup"),
    data_dir=os.getenv("AITA_DATA_DIR", os.path.join(BASE_DIR, "data")),
    admin_password=os.getenv("ADMIN_PASSWORD", ""),
    admin_emails=["chois@umn.edu", "mlevin@umn.edu"],
    cookie_name="aita_3102_auth",
    cookie_key=_google_cookie_key or "",
    redirect_uri=_google_redirect_uri or "http://localhost:30001",
    google_client_secret_file=_google_client_secret,
)
