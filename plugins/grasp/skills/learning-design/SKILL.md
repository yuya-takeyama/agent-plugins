---
name: learning-design
description: Design or review explainer content so the learner ends up able to explain, choose, or debug on their own, using evidence from cognitive and learning science. Use before writing any article, slide deck, narrated or dialogue video, quiz, course, or code walkthrough meant to teach someone, and when asked whether such a draft teaches well. Produces a design brief or a rubric review; the output format itself comes from the format skill (for example yes:explain or yes:course).
---

# learning-design

Content that feels clear is not the same as content that teaches. A fluent
explainer raises the learner's confidence without raising what they can do
unaided. Generated content makes this worse because it is cheap and polished.
This skill plans the learner's thinking, not the prose. Write for what the
learner must be able to do afterwards without the material and without AI.

Two entry points:

- **Designing.** Before any draft exists, write the brief below, then hand it
  to whatever skill renders the format. Keep the brief in the working
  directory as `learning-brief.md` so writers and reviewers share it.
- **Reviewing.** Grade an existing draft against
  [the rubric](references/rubric.md). Report each failed row with the location
  in the draft and the concrete fix. Fix the draft when asked to.

[The principles](references/principles.md) hold the evidence, boundary
conditions, and sources. Read the section for a decision when the brief needs
it. Do not quote effect sizes to the learner unless learning science is the
topic.

## The brief

Write each part as specific content about the topic, never as a description of
the content ("explains X" is not an objective).

1. **Learner.** Who they are, what they already know, which terms they lack.
   A guess is fine; label it. Prior knowledge decides most choices below.
2. **Objectives.** Two to five things the learner can do afterwards, each an
   observable act: explain why, choose between, predict what happens,
   find the bug in. Pick the few that matter and drop the rest.
3. **Misconceptions and confusable pairs.** The wrong models a half-informed
   learner holds, and the things they mix up. Each one is later used in a
   hook, a refutation, a dialogue line, or a distractor.
4. **Sequence per objective.** Pick one and say why:
   - Novice with the mechanism new to them: a worked example first, then
     faded practice.
   - Learner with enough prior knowledge to attempt it: a prediction or
     problem first, then the full explanation, then compare their attempt.
   - A misconception is likely: state it, refute it, then give the correct
     model.
   - Two confusable things: put them side by side, ask what differs, then
     name the principle.
   Introduce the names of parts before the mechanism that uses them. Ground an
   abstraction in a concrete case first, then strip the case away.
5. **Thinking points.** Where the learner predicts, recalls, explains why, or
   chooses, at least one per segment. Each is answered right after, in the
   material.
6. **Checks.** One or more items per objective, at the objective's level (a
   "choose" objective needs a scenario, not a definition). Distractors come
   from step 3. Feedback says why the right answer is right and what the
   tempting wrong one gets wrong. In a course, later checks reuse earlier
   lessons' concepts and mix confusable items.
7. **Cuts.** What you are leaving out, including interesting material that
   does not serve an objective.

## Presentation rules that apply to every format

- One claim per segment. Signal the structure: headings that state the claim,
  highlight or arrow on the part being discussed.
- Words sit next to, and play at the same time as, the picture part they
  describe.
- Cut decoration, off-topic anecdotes, and jokes that do not carry the point.
  An analogy states where it breaks.
- Talk to the learner in a conversational register.
- With narration over a dense diagram, show key terms on screen rather than
  the full sentence. Full captions stay available and can be switched off.
- A dialogue earns its place only when the learner character voices the
  misconception or asks the deep why or how question. Agreement and banter
  are cuts.
- Let the learner pause, replay, and jump between segments.

## Done

The brief or review is done when every objective has a sequence, a thinking
point, and an aligned check, and every misconception is used somewhere. Say
which rubric rows you could not check, such as pronunciation or real learner
results. No rubric pass shows that people learned; only their unaided
performance later does.
