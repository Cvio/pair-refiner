# 4. How the test run measures

Date: 2026-10-19. Decided with the user at the start of M6. BUILD.md says what the test run reports;
this is how each number is measured, on sentences that have a professional (reference) translation.

- **Scoring texts.** Both sides are tidied as usual, and for scoring only, Persian and Arabic-Indic digits
  count as Western digits. FLORES+ writes "4" in Persian text and some models write "۴"; neither should
  lose points for that.
- **Each translator:** corpus chrF of its translations against the references.
- **Each judge's accuracy:** for each sentence, the candidate with the highest sentence chrF against the
  reference counts as the right answer. A judge's first choice is the candidate it scored highest
  (meaning, then naturalness), its own model's candidate included, so a judge that favours its own work
  scores lower. A tie that includes the right answer counts as right. Accuracy is the share of sentences
  it got right.
- **Recommended top judge:** the judge with the best accuracy (list order breaks a tie).
- **The ensemble:** the sentences are refined again with the recommended top judge (translations and the
  panel come from the cache) and the winners' corpus chrF is compared with the best single translator's.
- **Recommended back-translation threshold:** the "truly bad" winners are the worst tenth by sentence chrF
  against the reference (at least one). Every midpoint between neighbouring back-translation chrF values
  is tried as a threshold. The one that best catches the bad winners while flagging few good ones (the
  highest F1) wins, with the lower one on a tie. The report also gives the share of rows it would flag.
