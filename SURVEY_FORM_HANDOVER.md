# Handover: build the AI-TA Consent + Start-of-Semester Survey (Google Form)

**For:** Google Gemini (Workspace) — please create ONE Google Form from this spec.

**Purpose:** consent + start-of-semester survey for the CEGE **3101** and **3102** AI Teaching
Assistant study (UMN). One form serves both courses; a "Course" question separates them.

## Form settings
- **Title:** CEGE 3101 & 3102 AI Teaching Assistant — Consent & Start-of-Semester Survey
- **Description:** "Please complete this before using the course AI Teaching Assistant. It includes a
  research consent form and a short survey (~2 minutes)."
- Restrict to **University of Minnesota (umn.edu)** accounts; **collect email addresses** (verified).
- **Link responses to a Google Sheet.**
- Limit to **1 response per person**; allow response editing.
- Show a section/progress indicator.

## Section 1 — Consent  *(make this its own section, shown first)*
- **Text block (paste verbatim):**

  > **⚠ DRAFT — NOT YET IRB-APPROVED.** Submit to the UMN IRB, replace every [bracketed] item,
  > and delete this banner before any student sees it.
  >
  > **Consent to Participate in Research**
  > **Study:** Evaluating an AI Teaching Assistant in CEGE 3101 and 3102
  > **Investigators:** Dr. Seongjin Choi (PI) and Dr. Michael Levin, Dept. of Civil,
  > Environmental, and Geo-Engineering, University of Minnesota. IRB study #: [_____].
  >
  > You are invited to take part in a research study on how an AI Teaching Assistant (AI TA)
  > affects student learning in CEGE 3101/3102, because you are enrolled in one of these courses.
  >
  > **What participation involves.** If you consent, we will use for research (a) your
  > interactions with the course AI TA (your questions and its responses) and (b) your answers to
  > this survey. Using the AI TA is optional and separate from consenting.
  >
  > **Voluntary.** Participation is completely voluntary. You may use the AI TA whether or not you
  > consent, and you may withdraw at any time. Your decision has **no effect on your grade** or
  > standing, and your instructors will not know who consented until after final grades are submitted.
  >
  > **Data & confidentiality.** Chat logs and survey responses are stored securely and analyzed in
  > de-identified form. Results may be reported only in aggregate; you will not be individually
  > identified. [Retention period and who has access — per your IRB protocol.]
  >
  > **Risks & benefits.** Risks are minimal. The AI TA can occasionally give incorrect or
  > incomplete information, so always verify its responses against course materials and your
  > instructor. There is no direct benefit to you; the study may help improve teaching tools.
  >
  > **Questions.** About the study: Dr. Seongjin Choi, chois@umn.edu. About your rights as a
  > participant: UMN IRB, irb@umn.edu or 612-626-5654.
  >
  > By selecting "Yes, I consent" below, you confirm that you have read this information, are 18 or
  > older, and agree to participate.
- **Question (required, multiple choice):**
  "I have read the information above and consent to participate in this research study."
  - Yes, I consent
  - No, I do not consent
  *(Note in help text: "You may use the AI TA either way; declining only excludes your data from the study.")*

## Section 2 — Survey
2. **Course** — multiple choice, **required**: `CEGE 3101` / `CEGE 3102`
3. **UMN Internet ID (x500)** — short answer, optional.
   Help text: "Used to link your survey to your de-identified tool usage. Type 'prefer not to' to opt out."
4. **Year** — multiple choice: 1st / 2nd / 3rd / 4th / 5th+ / Graduate
5. **Major** — short answer
6. **Prior probability/statistics coursework** — multiple choice: None / Some (1 course) / A lot (2+)
7. **Comfort using AI chatbots** (ChatGPT, Gemini, etc.) — linear scale **1–5** (1 = not at all, 5 = very comfortable)
8. **How often do you expect to use the AI TA?** — multiple choice:
   Daily / A few times a week / Weekly / Mainly before quizzes & exams / Rarely
9. **What do you hope the AI TA helps you with?** — paragraph, optional

### AI experience & attitudes  *(all optional)*
10. **How often do you use AI tools (ChatGPT, Gemini, etc.) in general?** — multiple choice:
    Daily / Weekly / Occasionally / Rarely / Never
11. **Which AI tools have you used?** — checkboxes: ChatGPT / Gemini / Claude / Microsoft Copilot / Other / None
12. **AI chatbots sometimes state incorrect information as if it were true ("hallucinate"). Were you aware of this?**
    — multiple choice: Yes, very aware / Somewhat / No
13. **How much do you trust AI chatbots' answers on course material?** — linear scale **1–5**
    (1 = not at all, 5 = completely)
14. **When an AI gives you an answer, how often do you check it against another source?** — multiple choice:
    Always / Usually / Sometimes / Rarely / Never

## After building
Reply with **both links**: the **edit** link and the **response (share)** link. The response link gets
added to each course's login page (`course_description` in `config.py`) so students see it on first sign-in.
