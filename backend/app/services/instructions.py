"""The 4.05.3 item 4 instructions page: "instructions to participants
regarding navigation through the course, course components, and course
completion."

Every number in the text is read from the constant that enforces it, so
the instructions can never drift from what the code actually does. Served
at /how-it-works and included in the audit bundle as
6-descriptive/how-it-works.md.
"""

from app.constants.assessment import PASSING_PCT, RETAKES_ALLOWED
from app.constants.enrollment import ENROLLMENT_DAYS


def how_it_works_markdown() -> str:
    return f"""# How a superCPE course works

superCPE offers self study CPE programs in two formats, with review
questions asked along the way and a qualified assessment at the end.

- A **study guide** course is text you read, section by section, with
  short videos that work through examples where they help.
- A **video** course is narrated video lessons.

A course may mix the two. Each lesson says which it is.

## Navigating a course

Your enrolled courses are listed under **My courses**. Open a course to
see its lessons in order, then open a lesson.

**A study guide lesson** opens as a reader. Read a section, answer the
review question that follows it, and the next section opens. The
glossary and any appendixes are reference material: they are available
from the start, are not required reading, and you can reach them at any
point from the course menu. That menu also has a search box that finds
any word in the guide, and a glossary lookup that takes you to the
definition of a key term.

**A video lesson** opens as a player, and your furthest point in it is
saved, so you can leave and pick up where you stopped.

## Review questions

Review questions are asked throughout each lesson — between sections of a
study guide, and at points inside a video. Answer one to continue; you are
told immediately whether your answer was correct, with an explanation
either way. Review questions are not scored toward passing, but **every
review question must be answered before the qualified assessment opens**.
You can re-answer a review question by revisiting the lesson.

## Videos inside a study guide

The videos in a study guide course add to what you have read — a worked
example, or commentary — rather than reading it aloud. There is nothing
to unlock: watch, skip, or replay them as you like. What must be answered
before the assessment opens is the review questions, not the videos.

## The qualified assessment

When every lesson's review questions are answered, the assessment becomes
available from the course page. It is a single form: answer every
question, then submit the whole assessment at once. Your answers are
saved as you go, so a closed browser loses nothing.

- A cumulative grade of at least **{PASSING_PCT} percent** is required to
  pass.
- If you do not pass, you may re-take the assessment up to
  **{RETAKES_ALLOWED} times** per enrollment. No feedback on individual
  questions is given for an assessment that was not passed; consider
  re-watching the lessons before trying again.
- The assessment must be completed before your enrollment expires,
  **{ENROLLMENT_DAYS} days** after enrollment. An expired enrollment
  cannot be extended; a new enrollment starts its own clock.

## Your certificate

Passing records your completion immediately: the credit earned, the
completion date, and a certificate number are yours from that moment. The
certificate of completion (PDF) is available to view and download from
the result page and from **My courses**. After passing, you may be asked
to evaluate the course; the evaluation is optional and your certificate
never depends on it.
"""
