"""The Persian tidy-up, on every Persian text going in or coming out (BUILD.md, "Persian text tidy-up").

Copied from volis's `volis/persian.py` (not imported: this repo shares nothing with volis). Its
letter table and spacing patterns are ported from hazm's normalizer
(https://github.com/roshan-research/hazm, `hazm/constants.py`, `hazm/normalizer.py`; MIT licence,
copyright (c) 2013 Alireza Nourian). What it does:

- Arabic look-alike letters become the Persian ones (ي -> ی, ك -> ک, and the rest of
  hazm's table), and ۀ becomes هٔ;
- Arabic-Indic digits (٠-٩) become Persian digits (۰-۹); Western digits stay;
- the half-space (ZWNJ, U+200C) is put back where a plain space was written: after the prefix
  mi- / nemi-, before -ha / -haye, -tar / -tarin, -gar / -gari, and before the endings
  (-am, -i, -id, -and, ...) after a word ending in ه. Those endings are joined only after ه,
  as volis does, so a separate word such as the ای of "ای خدا" is left alone.

Not copied from volis: its verb list (used there to split a mi- written joined to its verb; this
tool only replaces a space), and its link to volis's settings.
"""

import re

ZWNJ = "\u200c"

# hazm's TRANSLATION_SRC and TRANSLATION_DST, letters only: each character of
# the first is replaced by the character at the same place in the second.
_LOOKALIKE_FROM = (
    "\u0620\u063b\u063d\u063e\u063f\u0643\u064a\u066e\u066f\u0677\u0678\u0679\u067a\u067b\u067c\u067d"
    "\u067f\u0680\u0681\u0675\u0676\u0682\u0685\u0687\u0688\u0689\u068a\u068b\u068c\u068d\u068e\u068f"
    "\u0690\u0691\u0692\u0693\u0694\u0695\u0696\u0697\u0699\u069a\u069b\u069c\u069d\u069e\u069f\u06a0"
    "\u06a1\u06a2\u06a3\u06a4\u06a5\u06a6\u06a7\u06a8\u06aa\u06ab\u06ac\u06ad\u06ae\u06b0\u06b1\u06b2"
    "\u06b3\u06b4\u06b5\u06b6\u06b7\u06b8\u06b9\u06ba\u06bb\u06bc\u06bd\u06be\u06bf\u06c1\u06c2\u06c3"
    "\u06c4\u06c5\u06c6\u06c7\u06c8\u06c9\u06ca\u06cb\u06cf\u06cd\u06ce\u06d0\u06d1\u06d2\u06d3\u06d5"
    "\u06ee\u06ef\u06fa\u06fb\u06fc\u06ff\u0750\u0751\u0752\u0753\u0754\u0755\u0756\u0757\u0758\u0759"
    "\u075a\u075b\u075c\u075d\u075e\u075f\u0760\u0761\u0762\u0763\u0764\u0765\u0766\u0767\u0768\u0769"
    "\u076a\u076b\u076c\u076d\u076e\u076f\u0770\u0771\u0772\u0773\u0774\u0775\u0776\u0777\u0778\u0779"
    "\u077a\u077b\u077c\u077d\u077e\u077f\u08a0\u08a1\u08a2\u08a3\u08a4\u08a5\u08a6\u08a7\u08a8\u08a9"
    "\u08aa\u08ab\u08ae\u08af\u08b0\u08b1\u08ac\u08b2\u08b3\u08b4\u08b6\u08b7\u08b8\u08b9\u08ba\u08bb"
    "\u08bc\u08bd\ufb50\ufb51\ufb52\ufb53\ufb54\ufb55\ufb56\ufb57\ufb58\ufb59\ufb5a\ufb5b\ufb5c\ufb5d"
    "\ufb5e\ufb5f\ufb60\ufb61\ufb62\ufb63\ufb64\ufb65\ufb66\ufb67\ufb68\ufb69\ufb6e\ufb6f\ufb70\ufb71"
    "\ufb72\ufb73\ufb74\ufb75\ufb76\ufb77\ufb78\ufb79\ufb7a\ufb7b\ufb7c\ufb7d\ufb7e\ufb7f\ufb80\ufb81"
    "\ufb82\ufb83\ufb84\ufb85\ufb86\ufb87\ufb88\ufb89\ufb8a\ufb8b\ufb8c\ufb8d\ufb8e\ufb8f\ufb90\ufb91"
    "\ufb92\ufb93\ufb94\ufb95\ufb96\ufb97\ufb98\ufb99\ufb9a\ufb9b\ufb9c\ufb9d\ufb9e\ufb9f\ufba0\ufba1"
    "\ufba2\ufba3\ufba4\ufba5\ufba6\ufba7\ufba8\ufba9\ufbaa\ufbab\ufbac\ufbad\ufbae\ufbaf\ufbb0\ufbb1"
    "\ufe80\ufe81\ufe83\ufe84\ufe85\ufe86\ufe87\ufe88\ufe89\ufe8a\ufe8b\ufe8c\ufe8d\ufe8e\ufe8f\ufe90"
    "\ufe91\ufe92\ufe95\ufe96\ufe97\ufe98\ufe99\ufe9a\ufe9b\ufe9c\ufe9d\ufe9e\ufe9f\ufea0\ufea1\ufea2"
    "\ufea3\ufea4\ufea5\ufea6\ufea7\ufea8\ufea9\ufeaa\ufeab\ufeac\ufead\ufeae\ufeaf\ufeb0\ufeb1\ufeb2"
    "\ufeb3\ufeb4\ufeb5\ufeb6\ufeb7\ufeb8\ufeb9\ufeba\ufebb\ufebc\ufebd\ufebe\ufebf\ufec0\ufec1\ufec2"
    "\ufec3\ufec4\ufec5\ufec6\ufec7\ufec8\ufec9\ufeca\ufecb\ufecc\ufecd\ufece\ufecf\ufed0\ufed1\ufed2"
    "\ufed3\ufed4\ufed5\ufed6\ufed7\ufed8\ufed9\ufeda\ufedb\ufedc\ufedd\ufede\ufedf\ufee0\ufee1\ufee2"
    "\ufee3\ufee4\ufee5\ufee6\ufee7\ufee8\ufee9\ufeea\ufeeb\ufeec\ufeed\ufeee\ufeef\ufef0\ufef1\ufef2"
    "\ufef3\ufef4\u0649\ufe82\ufbfd\ufbfc"
)
_LOOKALIKE_TO = (
    "\u06cc\u06a9\u06cc\u06cc\u06cc\u06a9\u06cc\u0628\u0642\u0648\u06cc\u062a\u062a\u0628\u062a\u062a"
    "\u062a\u0628\u062d\u0627\u0648\u062d\u062d\u0686\u062f\u062f\u062f\u062f\u062f\u062f\u062f\u062f"
    "\u062f\u0631\u0631\u0631\u0631\u0631\u0631\u0631\u0631\u0633\u0633\u0633\u0635\u0635\u0637\u0639"
    "\u0641\u0641\u0641\u0641\u0641\u0641\u0642\u0642\u06a9\u06a9\u06a9\u06a9\u06a9\u06af\u06af\u06af"
    "\u06af\u06af\u0644\u0644\u0644\u0644\u0646\u0646\u0646\u0646\u0646\u0647\u0686\u0647\u0647\u0647"
    "\u0648\u0648\u0648\u0648\u0648\u0648\u0648\u0648\u0648\u06cc\u06cc\u06cc\u06cc\u06cc\u06cc\u0647"
    "\u062f\u0631\u0634\u0636\u063a\u0647\u0628\u0628\u0628\u0628\u0628\u0628\u0628\u062d\u062d\u062f"
    "\u062f\u0631\u0633\u0639\u0639\u0639\u0641\u0641\u06a9\u06a9\u06a9\u0645\u0645\u0646\u0646\u0646"
    "\u0644\u0631\u0631\u0633\u062d\u062d\u0633\u0631\u062d\u0627\u0627\u06cc\u06cc\u06cc\u0648\u0648"
    "\u06cc\u06cc\u062d\u0633\u0633\u06a9\u0628\u0628\u062c\u0637\u0641\u0642\u0644\u0645\u06cc\u06cc"
    "\u0631\u0648\u062f\u0635\u06af\u0648\u06cc\u0632\u0639\u06a9\u0628\u067e\u062a\u0631\u06cc\u0641"
    "\u0642\u0646\u0627\u0627\u0628\u0628\u0628\u0628\u067e\u067e\u067e\u067e\u0628\u0628\u0628\u0628"
    "\u062a\u062a\u062a\u062a\u062a\u062a\u062a\u062a\u062a\u062a\u062a\u062a\u0641\u0641\u0641\u0641"
    "\u062d\u062d\u062d\u062d\u062d\u062d\u062d\u062d\u0686\u0686\u0686\u0686\u0686\u0686\u0686\u0686"
    "\u062f\u062f\u062f\u062f\u062f\u062f\u062f\u062f\u0698\u0698\u0631\u0631\u06a9\u06a9\u06a9\u06a9"
    "\u06af\u06af\u06af\u06af\u06af\u06af\u06af\u06af\u06af\u06af\u06af\u06af\u0646\u0646\u0646\u0646"
    "\u0646\u0646\u0647\u0647\u0647\u0647\u0647\u0647\u0647\u0647\u0647\u0647\u06cc\u06cc\u06cc\u06cc"
    "\u0621\u0627\u0627\u0627\u0648\u0648\u0627\u0627\u06cc\u06cc\u06cc\u06cc\u0627\u0627\u0628\u0628"
    "\u0628\u0628\u062a\u062a\u062a\u062a\u062b\u062b\u062b\u062b\u062c\u062c\u062c\u062c\u062d\u062d"
    "\u062d\u062d\u062e\u062e\u062e\u062e\u062f\u062f\u0630\u0630\u0631\u0631\u0632\u0632\u0633\u0633"
    "\u0633\u0633\u0634\u0634\u0634\u0634\u0635\u0635\u0635\u0635\u0636\u0636\u0636\u0636\u0637\u0637"
    "\u0637\u0637\u0638\u0638\u0638\u0638\u0639\u0639\u0639\u0639\u063a\u063a\u063a\u063a\u0641\u0641"
    "\u0641\u0641\u0642\u0642\u0642\u0642\u06a9\u06a9\u06a9\u06a9\u0644\u0644\u0644\u0644\u0645\u0645"
    "\u0645\u0645\u0646\u0646\u0646\u0646\u0647\u0647\u0647\u0647\u0648\u0648\u06cc\u06cc\u06cc\u06cc"
    "\u06cc\u06cc\u06cc\u0627\u06cc\u06cc"
)
_TABLE = str.maketrans(_LOOKALIKE_FROM, _LOOKALIKE_TO)
_TABLE[0x06C0] = "\u0647\u0654"  # heh with yeh above -> heh + hamza above
_TABLE.update({0x0660 + n: 0x06F0 + n for n in range(10)})  # Arabic-Indic digits -> Persian digits

_PUNC_AFTER = r"\.:!\u060c\u061b\u061f\u00bb\]\)\}"
_PUNC_BEFORE = r"\u00ab\[\(\{"
_LETTERS = "\u0622\u0627\u0628\u067e\u062a\u062b\u062c\u0686\u062d\u062e\u062f\u0630\u0631\u0632\u0698\u0633\u0634\u0635\u0636\u0637\u0638\u0639\u063a\u0641\u0642\u06a9\u06af\u0644\u0645\u0646\u0648\u0647\u06cc"

# hazm's EXTRA_SPACE_PATTERNS, the ones about spaces, ZWNJ and tatweel.
_TIDY = [(re.compile(p), r) for p, r in [
    (r"[\u0640\r]", ""),  # tatweel (the stretching line), carriage returns
    (r" {2,}", " "),
    (r"\u200c{2,}", ZWNJ),
    (r"\u200c+ ", " "),
    (r" \u200c+", " "),
    (r"^[ \u200c]+|[ \u200c]+$", ""),
]]

# hazm's AFFIX_SPACING_PATTERNS.
_AFFIXES = [(re.compile(p), r) for p, r in [
    (r"([^ ]\u0647) \u06cc ", r"\1" + ZWNJ + "\u06cc "),  # the ezafe ye after a word ending in heh
    (r"(?<=[^\n\d " + _PUNC_AFTER + _PUNC_BEFORE + r"]{2}) "
     r"(\u062a\u0631(\u06cc\u0646?)?|\u06af\u0631\u06cc?|\u0647\u0627(?:\u06cc\u06cc?)?)(?=[ \n" + _PUNC_AFTER + _PUNC_BEFORE + r"]|$)",
     ZWNJ + r"\1"),  # -tar / -tarin, -gar / -gari, -ha / -haye / -haii written apart
    (r"([^ ]\u0647) (\u0627(\u0645|\u06cc\u0645|\u0634|\u0646\u062f|\u06cc|\u06cc\u062f|\u062a))(?=[ \n" + _PUNC_AFTER + r"]|$)",
     r"\1" + ZWNJ + r"\2"),  # the endings after a word ending in heh
    (r"(\u0647)(\u0647\u0627)", r"\1" + ZWNJ + r"\2"),  # -ha joined straight onto a heh
]]

# mi- / nemi- written apart from the word after it, joined as hazm does. Without volis's verb list
# this also joins the rare non-verb, such as "\u0645\u0627\u0647 \u0645\u06cc \u0633\u0627\u0644" (the month of May).
_MI_APART = re.compile(r"(^| )(\u0646?\u0645\u06cc) ([" + _LETTERS + r"]+)")


# The older spelling ائی at the end of a word (هائی, جدائی) as the modern ایی. Not in volis: MIZAN uses
# it a lot. Inside a word (اسرائیل) it is left alone. A missing madda (اخر for آخر) isn't added: no
# rule can tell where it belongs, so that is left to the judges.
_OLD_AII = re.compile(r"ائی(?![" + _LETTERS + r"ئ])")


def tidy(text: str) -> str:
    """Persian text with the look-alike letters, the digits and the half-spaces put right."""
    text = _OLD_AII.sub("ایی", text.translate(_TABLE))
    for pattern, replacement in _TIDY + _AFFIXES:
        text = pattern.sub(replacement, text)
    return _MI_APART.sub(lambda m: f"{m.group(1)}{m.group(2)}{ZWNJ}{m.group(3)}", text)
