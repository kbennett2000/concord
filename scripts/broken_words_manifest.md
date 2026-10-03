# Broken- and glued-word cleanup manifest

Written by [fix_broken_words.py](fix_broken_words.py). Every change is a row of [broken_words_manifest.csv](broken_words_manifest.csv): translation, reference, the character offset of the edit in the verse as it stood, kind, the text before and after (with a word of context each side), and the evidence — how often the repaired word (or, for a glued pair, the two-word phrase) stands in that translation, and how many sibling verses print it.

**28365 changes** in 26994 verses. Kinds: `split` — a word split by a stray space; `hyphen` — a stray space beside a hyphen; `apostrophe` — one inside a possessive; `glued` — two words run together; `punctuation` — no space after a sentence's mark.

| Translation | split | hyphen | apostrophe | glued | punctuation | Changes | Verses |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| AKJV | 1,728 | 14 | 2 | 0 | 0 | 1,744 | 1,741 |
| ASV | 1,708 | 1,000 | 4 | 3 | 66 | 2,781 | 2,572 |
| CPDV | 1,903 | 392 | 0 | 2 | 0 | 2,297 | 2,233 |
| DBT | 1,750 | 1,157 | 1 | 0 | 0 | 2,908 | 2,680 |
| DRB | 1,765 | 93 | 3 | 8 | 0 | 1,869 | 1,855 |
| ERV | 1,794 | 412 | 1 | 0 | 0 | 2,207 | 2,153 |
| JPS | 1,790 | 1,118 | 5 | 0 | 0 | 2,913 | 2,696 |
| KJV | 1,839 | 3 | 3 | 0 | 0 | 1,845 | 1,844 |
| SLT | 1,675 | 419 | 2 | 1 | 0 | 2,097 | 2,046 |
| WBT | 1,755 | 1,091 | 0 | 0 | 1 | 2,847 | 2,631 |
| WEB | 1,646 | 245 | 1 | 0 | 0 | 1,892 | 1,850 |
| YLT | 1,667 | 1,296 | 1 | 1 | 0 | 2,965 | 2,693 |

## Left alone (1421)

| Reason | Cases |
| --- | ---: |
| both halves are words | 621 |
| the joined form is printed nowhere else | 394 |
| thin evidence: the word stands alone fewer than three times and no sibling prints it | 172 |
| line-break hyphen: the word is printed solid, so the hyphen would have to go too | 133 |
| a one-letter word, and the joined word is not attested beside its neighbours | 51 |
| no sibling prints the two words | 22 |
| a one-letter word beside a word printed elsewhere | 19 |
| printed as a compound or the translation's own spelling, not two words | 9 |

| Translation | Reference | Kind | As printed | Reason |
| --- | --- | --- | --- | --- |
| AKJV | Gen 10:15 | split | first born, | both halves are words |
| AKJV | Gen 19:37 | split | first born | both halves are words |
| AKJV | Gen 27:19 | split | first born; | both halves are words |
| AKJV | Gen 43:33 | split | first born | both halves are words |
| AKJV | Exod 6:8 | split | in to | both halves are words |
| AKJV | Exod 33:20 | split | can not | both halves are words |
| AKJV | Exod 34:2 | split | your self | both halves are words |
| AKJV | Exod 40:15 | split | a noint | a one-letter word, and the joined word is not attested beside its neighbours |
| AKJV | Num 15:25 | split | for given | both halves are words |
| AKJV | Deut 14:26 | split | house hold, | both halves are words |
| AKJV | 1 Sam 20:41 | split | a rose | both halves are words |
| AKJV | 1 Kgs 12:27 | split | a gain | both halves are words |
| AKJV | 2 Kgs 3:25 | split | a bout | a one-letter word beside a word printed elsewhere |
| AKJV | 2 Kgs 19:26 | split | house tops, | both halves are words |
| AKJV | 1 Chr 1:17 | split | a nd | a one-letter word, and the joined word is not attested beside its neighbours |
| AKJV | 1 Chr 9:33 | split | fat hers | both halves are words |
| AKJV | 1 Chr 25:13 | split | to B | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| AKJV | 2 Chr 1:8 | split | fat her, | both halves are words |
| AKJV | 2 Chr 10:9 | split | fat her | both halves are words |
| AKJV | Ps 87:4 | split | Philisti a, | a one-letter word, and the joined word is not attested beside its neighbours |
| AKJV | Isa 30:14 | split | with out | both halves are words |
| AKJV | Isa 33:19 | split | can not | both halves are words |
| AKJV | Isa 55:2 | split | satisfi es | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| AKJV | Jer 26:20 | split | Shem aiah | both halves are words |
| AKJV | Jer 46:27 | split | be hold, | both halves are words |
| AKJV | Jer 50:12 | split | a shamed: | both halves are words |
| AKJV | Ezek 14:22 | split | be hold, | both halves are words |
| AKJV | Ezek 36:26 | split | wit hin | both halves are words |
| AKJV | Ezek 37:21 | split | heat hen, | both halves are words |
| AKJV | Ezek 38:13 | split | a way | both halves are words |
| AKJV | Ezek 40:29 | split | there of, | both halves are words |
| AKJV | Hab 1:13 | split | can not | both halves are words |
| AKJV | Matt 5:36 | split | can not | both halves are words |
| AKJV | Mark 12:41 | split | be held | both halves are words |
| AKJV | John 4:43 | split | in to | both halves are words |
| AKJV | John 9:40 | split | a lso? | a one-letter word, and the joined word is not attested beside its neighbours |
| AKJV | John 11:7 | split | a gain. | both halves are words |
| AKJV | Acts 2:42 | split | fellow ship, | both halves are words |
| AKJV | Acts 19:8 | split | a nd | a one-letter word, and the joined word is not attested beside its neighbours |
| AKJV | Acts 27:10 | split | a nd | a one-letter word, and the joined word is not attested beside its neighbours |
| AKJV | 2 Cor 3:10 | split | exc els. | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| AKJV | Gal 6:3 | split | him self | both halves are words |
| AKJV | Rev 2:2 | split | can not | both halves are words |
| ASV | Gen 11:31 | hyphen | hter-in- law, | the joined form is printed nowhere else |
| ASV | Gen 14:22 | split | lift ed | both halves are words |
| ASV | Gen 24:56 | split | a way | both halves are words |
| ASV | Gen 40:6 | split | be hold, | both halves are words |
| ASV | Gen 50:3 | hyphen | three- score | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| ASV | Exod 2:18 | split | so on | both halves are words |
| ASV | Exod 21:27 | hyphen | man- servant’s | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| ASV | Exod 25:29 | split | there of, | both halves are words |
| ASV | Exod 37:23 | split | there of, | both halves are words |
| ASV | Lev 5:16 | split | there to, | both halves are words |
| ASV | Lev 11:13 | hyphen | gier -eagle, | the joined form is printed nowhere else |
| ASV | Num 7:37 | hyphen | l- offering; | the joined form is printed nowhere else |
| ASV | Num 17:2 | split | fat hers’ | both halves are words |
| ASV | Num 24:6 | hyphen | lign- aloes | the joined form is printed nowhere else |
| ASV | Num 31:18 | hyphen | women- children, | the joined form is printed nowhere else |
| ASV | Deut 7:7 | split | up on | both halves are words |
| ASV | Deut 14:12 | hyphen | gier- eagle, | the joined form is printed nowhere else |
| ASV | Josh 1:5 | split | for sake | both halves are words |
| ASV | Judg 10:1 | glued | hillcountry | printed as a compound or the translation's own spelling, not two words |
| ASV | Judg 20:48 | split | more over | both halves are words |
| ASV | 1 Sam 1:7 | split | ye ar, | both halves are words |
| ASV | 1 Sam 9:15 | split | reveal ed | both halves are words |
| ASV | 1 Sam 19:4 | hyphen | thee -ward | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| ASV | 1 Sam 30:8 | split | over take | both halves are words |
| ASV | 1 Sam 30:25 | split | for ward, | both halves are words |
| ASV | 2 Sam 1:24 | split | scar let | both halves are words |
| ASV | 1 Kgs 16:8 | split | beg an | both halves are words |
| ASV | 2 Chr 7:18 | split | covenant ed | both halves are words |
| ASV | 2 Chr 17:19 | split | be sides | both halves are words |
| ASV | 2 Chr 19:7 | split | he ed | both halves are words |
| ASV | Ezra 8:31 | hyphen | lier- in-wait | the joined form is printed nowhere else |
| ASV | Esth 2:3 | split | chamber lain, | both halves are words |
| ASV | Ps 22:1 | hyphen | hash- Shahar. | the joined form is printed nowhere else |
| ASV | Ps 52:7 | split | trust ed | both halves are words |
| ASV | Prov 20:26 | hyphen | threshing- wheel | the joined form is printed nowhere else |
| ASV | Eccl 10:17 | split | sea son, | both halves are words |
| ASV | Isa 7:19 | hyphen | thorn -hedges, | the joined form is printed nowhere else |
| ASV | Isa 15:5 | hyphen | Eglath- shelishi-yah: | the joined form is printed nowhere else |
| ASV | Isa 34:15 | hyphen | dart -snake | the joined form is printed nowhere else |
| ASV | Isa 44:14 | hyphen | holm -tree | the joined form is printed nowhere else |
| ASV | Isa 47:13 | hyphen | star -gazers, | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| ASV | Jer 23:11 | split | a re | a one-letter word, and the joined word is not attested beside its neighbours |
| ASV | Jer 37:16 | hyphen | dungeon- house, | the joined form is printed nowhere else |
| ASV | Jer 46:2 | hyphen | Pharaoh -neco | the joined form is printed nowhere else |
| ASV | Jer 50:15 | split | her self; | both halves are words |
| ASV | Jer 51:20 | hyphen | battle -axe | the joined form is printed nowhere else |
| ASV | Ezek 17:15 | split | a mbassadors | a one-letter word, and the joined word is not attested beside its neighbours |
| ASV | Ezek 23:11 | split | O holibah | a one-letter word, and the joined word is not attested beside its neighbours |
| ASV | Ezek 31:3 | hyphen | forest -like | the joined form is printed nowhere else |
| ASV | Ezek 47:19 | hyphen | Meriboth -kadesh, | the joined form is printed nowhere else |
| ASV | Ezek 48:20 | hyphen | four -square, | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| ASV | Dan 4:11 | split | there of | both halves are words |
| ASV | Amos 6:6 | split | them selves | both halves are words |
| ASV | Mic 6:16 | split | there of | both halves are words |
| ASV | Matt 12:24 | split | he ard | both halves are words |
| ASV | Matt 14:20 | split | fill ed: | both halves are words |
| ASV | Matt 16:17 | hyphen | Bar -Jonah: | the joined form is printed nowhere else |
| ASV | Mark 4:24 | split | he ed | both halves are words |
| ASV | Mark 4:33 | split | he ar | both halves are words |
| ASV | John 3:27 | split | he aven. | both halves are words |
| ASV | John 9:21 | split | him self. | both halves are words |
| ASV | Acts 10:7 | hyphen | household- servants, | the joined form is printed nowhere else |
| ASV | Acts 13:1 | hyphen | foster -brother | the joined form is printed nowhere else |
| ASV | Acts 20:21 | split | to ward | both halves are words |
| ASV | Acts 25:11 | hyphen | wrong- doer, | the joined form is printed nowhere else |
| ASV | Acts 27:17 | hyphen | under -girding | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| ASV | Rom 1:31 | hyphen | covenant -breakers, | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| ASV | Rom 5:20 | split | a bound | both halves are words |
| ASV | 2 Cor 1:11 | split | bestow ed | both halves are words |
| ASV | 1 Tim 3:16 | split | manifest ed | both halves are words |
| BSB | Exod 8:4 | split | up on | both halves are words |
| BSB | Exod 19:12 | split | up on | both halves are words |
| BSB | Exod 25:37 | split | up on | both halves are words |
| BSB | Exod 34:2 | split | up on | both halves are words |
| BSB | Lev 2:12 | split | up on | both halves are words |
| BSB | Num 21:28 | split | a blaze | a one-letter word beside a word printed elsewhere |
| BSB | Num 35:30 | split | a lone | a one-letter word, and the joined word is not attested beside its neighbours |
| BSB | Deut 17:6 | split | a lone | a one-letter word, and the joined word is not attested beside its neighbours |
| BSB | Deut 19:15 | split | A lone | a one-letter word, and the joined word is not attested beside its neighbours |
| BSB | Josh 2:8 | split | up on | both halves are words |
| BSB | Judg 6:28 | split | up on | both halves are words |
| BSB | 2 Kgs 23:12 | split | up on | both halves are words |
| BSB | Ezra 4:24 | glued | standstill | no sibling prints the two words |
| BSB | Neh 12:31 | split | up on | both halves are words |
| BSB | Ps 102:7 | split | a lone | a one-letter word, and the joined word is not attested beside its neighbours |
| BSB | Isa 47:11 | split | to ward | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| BSB | Isa 60:7 | split | up on | both halves are words |
| BSB | Jer 10:10 | split | earth quakes | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| BSB | Jer 51:29 | split | earth quakes | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| BSB | Lam 2:14 | split | to ward | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| BSB | Ezek 2:1 | split | up on | both halves are words |
| BSB | Joel 2:10 | split | earth quakes; | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| BSB | Amos 4:11 | split | a blaze, | a one-letter word beside a word printed elsewhere |
| BSB | Rev 3:2 | glued | incomplete | no sibling prints the two words |
| CPDV | Gen 19:10 | split | in to | both halves are words |
| CPDV | Gen 25:18 | split | as Shur, | both halves are words |
| CPDV | Gen 34:7 | split | be cause | both halves are words |
| CPDV | Gen 35:23 | split | first born, | both halves are words |
| CPDV | Gen 38:6 | split | first born | both halves are words |
| CPDV | Gen 38:7 | split | first born | both halves are words |
| CPDV | Gen 39:20 | split | ki ng | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| CPDV | Gen 45:28 | split | a live. | both halves are words |
| CPDV | Exod 6:4 | split | Cana an, | both halves are words |
| CPDV | Exod 12:23 | split | door posts, | both halves are words |
| CPDV | Exod 21:8 | split | author ity | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| CPDV | Exod 21:18 | split | quar reled, | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| CPDV | Exod 21:30 | split | what ever | both halves are words |
| CPDV | Exod 28:4 | hyphen | close -fit | the joined form is printed nowhere else |
| CPDV | Exod 34:16 | split | them selves | both halves are words |
| CPDV | Exod 40:36 | split | depart ed | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| CPDV | Lev 1:11 | split | a round. | both halves are words |
| CPDV | Lev 13:39 | hyphen | white- colored | the joined form is printed nowhere else |
| CPDV | Lev 18:6 | hyphen | blood- relative | the joined form is printed nowhere else |
| CPDV | Lev 19:32 | hyphen | gray- haired | the joined form is printed nowhere else |
| CPDV | Lev 20:11 | split | up on | both halves are words |
| CPDV | Lev 20:27 | hyphen | oracle -like | the joined form is printed nowhere else |
| CPDV | Num 1:10 | split | Elisham a | a one-letter word beside a word printed elsewhere |
| CPDV | Num 9:1 | split | fir st | both halves are words |
| CPDV | Num 11:1 | hyphen | grief- stricken | the joined form is printed nowhere else |
| CPDV | Num 11:29 | split | de cides | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| CPDV | Num 28:11 | split | fir st | both halves are words |
| CPDV | Num 32:27 | hyphen | well -equipped, | the joined form is printed nowhere else |
| CPDV | Deut 1:7 | hyphen | low -lying | the joined form is printed nowhere else |
| CPDV | Deut 28:59 | hyphen | long -lasting, | the joined form is printed nowhere else |
| CPDV | Deut 31:7 | split | fat hers, | both halves are words |
| CPDV | Josh 7:5 | split | flee ing | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| CPDV | Josh 11:13 | hyphen | highly- fortified | the joined form is printed nowhere else |
| CPDV | Josh 22:15 | split | withdraw ing | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| CPDV | Ruth 2:22 | split | a s | a one-letter word, and the joined word is not attested beside its neighbours |
| CPDV | 1 Sam 14:31 | split | A ijalon. | a one-letter word, and the joined word is not attested beside its neighbours |
| CPDV | 1 Sam 27:11 | split | thin gs. | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| CPDV | 2 Sam 1:23 | split | be loved, | both halves are words |
| CPDV | 2 Sam 10:19 | hyphen | fifty- eight | the joined form is printed nowhere else |
| CPDV | 2 Sam 14:16 | split | we re | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| CPDV | 2 Sam 18:20 | split | be cause | both halves are words |
| CPDV | 2 Sam 20:20 | split | ca st | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| CPDV | 2 Sam 23:4 | glued | rainfall | no sibling prints the two words |
| CPDV | 1 Kgs 16:31 | hyphen | Eth- baal, | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| CPDV | 2 Kgs 3:27 | split | prompt ly | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| CPDV | 2 Kgs 5:2 | split | a way | both halves are words |
| CPDV | 2 Kgs 7:4 | glued | anyway | no sibling prints the two words |
| CPDV | 2 Kgs 17:30 | hyphen | Soccoth- benoth; | the joined form is printed nowhere else |
| CPDV | 2 Kgs 17:31 | hyphen | Anam- melech. | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| CPDV | 1 Chr 4:18 | split | fat her | both halves are words |
| CPDV | 1 Chr 17:19 | split | he art, | both halves are words |
| CPDV | 1 Chr 28:18 | split | wi th | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| CPDV | 2 Chr 28:8 | split | a way | both halves are words |
| CPDV | 2 Chr 33:25 | split | Am on, | both halves are words |
| CPDV | Neh 13:28 | split | a s | a one-letter word, and the joined word is not attested beside its neighbours |
| CPDV | Esth 7:9 | split | up on | both halves are words |
| CPDV | Job 20:25 | split | she ath, | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| CPDV | Ps 35:19 | split | gl ad | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| CPDV | Ps 38:16 | split | be ing | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| CPDV | Prov 24:12 | split | pre serves | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| CPDV | Isa 2:12 | hyphen | self -exalted, | the joined form is printed nowhere else |
| CPDV | Isa 15:5 | hyphen | three -year-old | the joined form is printed nowhere else |
| CPDV | Isa 21:9 | hyphen | two- horse | the joined form is printed nowhere else |
| CPDV | Isa 36:22 | split | enter ed | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| CPDV | Isa 58:1 | split | a cts, | a one-letter word, and the joined word is not attested beside its neighbours |
| CPDV | Jer 2:37 | split | de part | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| CPDV | Jer 23:12 | split | for ward, | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| CPDV | Jer 31:10 | split | a mid | a one-letter word beside a word printed elsewhere |
| CPDV | Jer 35:14 | split | instruct ed | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| CPDV | Jer 42:14 | split | fa mine. | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| CPDV | Lam 1:8 | split | be cause | both halves are words |
| CPDV | Ezek 17:11 | split | le ad | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| CPDV | Ezek 23:22 | split | O holibah, | a one-letter word, and the joined word is not attested beside its neighbours |
| CPDV | Ezek 23:24 | hyphen | well -equipped | the joined form is printed nowhere else |
| CPDV | Ezek 33:13 | split | confide nce | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| CPDV | Ezek 40:27 | split | in ner | both halves are words |
| CPDV | Dan 5:6 | hyphen | self- control, | the joined form is printed nowhere else |
| CPDV | Hos 10:4 | split | de al. | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| CPDV | Joel 2:3 | split | a lush | a one-letter word beside a word printed elsewhere |
| CPDV | Obad 1:5 | hyphen | grape -pickers | the joined form is printed nowhere else |
| CPDV | Jonah 3:10 | split | be en | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| CPDV | Mic 3:12 | split | be cause | both halves are words |
| CPDV | Nah 3:17 | glued | alight | printed as a compound or the translation's own spelling, not two words |
| CPDV | Nah 3:18 | split | drow sy, | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| CPDV | Hab 3:7 | hyphen | tent -skins | the joined form is printed nowhere else |
| CPDV | Matt 12:25 | split | it self | both halves are words |
| CPDV | Matt 13:8 | split | hundred fold, | both halves are words |
| CPDV | Matt 17:13 | split | under stood | both halves are words |
| CPDV | Matt 24:15 | split | se en | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| CPDV | Mark 14:12 | split | fir st | both halves are words |
| CPDV | Mark 16:9 | split | fir st | both halves are words |
| CPDV | Luke 13:2 | split | be cause | both halves are words |
| CPDV | Luke 20:5 | split | them selves, | both halves are words |
| CPDV | Luke 23:12 | split | be came | both halves are words |
| CPDV | Acts 25:18 | split | a ccusation | a one-letter word, and the joined word is not attested beside its neighbours |
| CPDV | Rom 1:20 | split | under stood | both halves are words |
| CPDV | Rom 12:12 | hyphen | ever -willing; | the joined form is printed nowhere else |
| CPDV | 1 Cor 1:20 | hyphen | truth -seekers | the joined form is printed nowhere else |
| CPDV | 1 Cor 12:28 | hyphen | miracle- workers, | the joined form is printed nowhere else |
| CPDV | 2 Cor 5:16 | split | long er. | both halves are words |
| CPDV | 2 Cor 6:8 | hyphen | truth- tellers, | the joined form is printed nowhere else |
| CPDV | Phil 2:25 | hyphen | co- worker, | the joined form is printed nowhere else |
| CPDV | Phil 4:11 | split | st ate | both halves are words |
| CPDV | 2 Thess 3:7 | split | your selves | both halves are words |
| CPDV | 2 Tim 2:22 | split | he art. | both halves are words |
| CPDV | 2 Tim 3:4 | hyphen | self- important, | the joined form is printed nowhere else |
| CPDV | Heb 6:6 | split | si nce | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| CPDV | Heb 7:9 | split | a t | a one-letter word, and the joined word is not attested beside its neighbours |
| CPDV | Jas 1:21 | hyphen | newly- grafted | the joined form is printed nowhere else |
| CPDV | 1 Pet 1:1 | hyphen | newly -arrived | the joined form is printed nowhere else |
| CPDV | Rev 8:13 | split | a lone | a one-letter word, and the joined word is not attested beside its neighbours |
| CPDV | Rev 9:13 | split | a lone | a one-letter word, and the joined word is not attested beside its neighbours |
| DBT | Gen 13:10 | split | a ll | both halves are words |
| DBT | Gen 14:1 | hyphen | El -lasar, | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| DBT | Gen 14:5 | hyphen | Shaveh- Kirjathaim, | the joined form is printed nowhere else |
| DBT | Gen 14:23 | hyphen | sandal -thong, | the joined form is printed nowhere else |
| DBT | Gen 28:11 | split | ma de | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| DBT | Gen 30:38 | hyphen | watering- places | the joined form is printed nowhere else |
| DBT | Gen 41:4 | hyphen | fine -looking | the joined form is printed nowhere else |
| DBT | Gen 41:10 | hyphen | life -guard’s | the joined form is printed nowhere else |
| DBT | Gen 44:2 | hyphen | grain- money. | the joined form is printed nowhere else |
| DBT | Exod 2:7 | hyphen | wet -nurse | the joined form is printed nowhere else |
| DBT | Exod 12:9 | hyphen | in -wards. | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| DBT | Exod 29:22 | hyphen | fat -tail, | the joined form is printed nowhere else |
| DBT | Exod 30:16 | hyphen | atonement -money | the joined form is printed nowhere else |
| DBT | Exod 35:5 | hyphen | heave -offering—gold, | the joined form is printed nowhere else |
| DBT | Exod 35:15 | hyphen | anointing- oil, | the joined form is printed nowhere else |
| DBT | Exod 35:15 | hyphen | entrance -curtain | the joined form is printed nowhere else |
| DBT | Lev 3:1 | hyphen | peace -offering,—if | the joined form is printed nowhere else |
| DBT | Lev 7:1 | hyphen | trespass -offering—it | the joined form is printed nowhere else |
| DBT | Lev 11:35 | split | where upon | both halves are words |
| DBT | Lev 26:5 | hyphen | sowing- time; | the joined form is printed nowhere else |
| DBT | Lev 26:32 | split | there in | both halves are words |
| DBT | Num 5:7 | split | a ccording | a one-letter word, and the joined word is not attested beside its neighbours |
| DBT | Num 5:14 | hyphen | barley- meal; | the joined form is printed nowhere else |
| DBT | Num 12:14 | glued | anyways | no sibling prints the two words |
| DBT | Num 15:3 | split | offer ing, | both halves are words |
| DBT | Num 15:32 | split | gather ing | both halves are words |
| DBT | Num 19:17 | hyphen | purification -offering | the joined form is printed nowhere else |
| DBT | Num 24:6 | hyphen | aloe -trees | the joined form is printed nowhere else |
| DBT | Num 25:8 | hyphen | tent -chamber, | the joined form is printed nowhere else |
| DBT | Num 31:6 | hyphen | alarm -trumpets | the joined form is printed nowhere else |
| DBT | Deut 10:6 | hyphen | Beeroth- Bene-Jaakan | the joined form is printed nowhere else |
| DBT | Deut 15:10 | hyphen | evil -disposed | the joined form is printed nowhere else |
| DBT | Deut 32:46 | split | he arts | both halves are words |
| DBT | Josh 2:15 | hyphen | city- wall, | the joined form is printed nowhere else |
| DBT | Josh 6:5 | hyphen | blast -horn, | the joined form is printed nowhere else |
| DBT | Josh 10:2 | split | great er | both halves are words |
| DBT | Josh 10:11 | hyphen | Beth -horon,—that | the joined form is printed nowhere else |
| DBT | Josh 12:8 | hyphen | hill -slopes, | the joined form is printed nowhere else |
| DBT | Josh 19:9 | split | inherit ed | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| DBT | Judg 8:35 | hyphen | Jerubbaal -Gideon, | the joined form is printed nowhere else |
| DBT | 1 Sam 5:4 | hyphen | fish- stump | the joined form is printed nowhere else |
| DBT | 1 Sam 6:12 | split | high way, | both halves are words |
| DBT | 1 Sam 12:2 | hyphen | grey- headed; | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| DBT | 1 Sam 14:14 | hyphen | half -furrow | the joined form is printed nowhere else |
| DBT | 1 Sam 17:5 | split | corse let | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| DBT | 1 Kgs 6:6 | split | out side, | both halves are words |
| DBT | 1 Kgs 7:26 | hyphen | lily- blossoms; | the joined form is printed nowhere else |
| DBT | 1 Kgs 15:34 | split | where with | both halves are words |
| DBT | 2 Kgs 12:6 | split | ho use. | both halves are words |
| DBT | 2 Kgs 19:29 | split | ye ar | both halves are words |
| DBT | 1 Chr 2:54 | hyphen | -Hammana- hethites, | the joined form is printed nowhere else |
| DBT | 1 Chr 2:54 | hyphen | Hazi -Hammana- | the joined form is printed nowhere else |
| DBT | 1 Chr 4:21 | hyphen | byssus -workers, | the joined form is printed nowhere else |
| DBT | 1 Chr 7:35 | split | a nd | a one-letter word, and the joined word is not attested beside its neighbours |
| DBT | 1 Chr 9:27 | split | up on | both halves are words |
| DBT | 1 Chr 10:13 | split | a sking | a one-letter word, and the joined word is not attested beside its neighbours |
| DBT | 1 Chr 12:23 | split | equip ped | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| DBT | 2 Chr 4:5 | hyphen | lily- blossoms; | the joined form is printed nowhere else |
| DBT | 2 Chr 16:13 | hyphen | one -and-fortieth | the joined form is printed nowhere else |
| DBT | 2 Chr 26:14 | hyphen | slinging -stones. | the joined form is printed nowhere else |
| DBT | 2 Chr 30:22 | hyphen | feast -offerings | the joined form is printed nowhere else |
| DBT | Ps 36:4 | split | up on | both halves are words |
| DBT | Ps 41:6 | split | it self: | both halves are words |
| DBT | Ps 84:6 | hyphen | well -spring; | the joined form is printed nowhere else |
| DBT | Ps 104:13 | hyphen | upper -chambers: | the joined form is printed nowhere else |
| DBT | Ps 128:3 | hyphen | olive -plants | the joined form is printed nowhere else |
| DBT | Prov 30:13 | hyphen | jaw -teeth | the joined form is printed nowhere else |
| DBT | Eccl 12:5 | hyphen | age -long | the joined form is printed nowhere else |
| DBT | Song 5:9 | split | be loved | both halves are words |
| DBT | Isa 3:20 | hyphen | scent -boxes, | the joined form is printed nowhere else |
| DBT | Isa 3:24 | hyphen | well -set | the joined form is printed nowhere else |
| DBT | Isa 7:19 | hyphen | thorn -bushes, | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| DBT | Isa 15:5 | hyphen | Eglath -Sheli-shijah: | the joined form is printed nowhere else |
| DBT | Isa 17:9 | hyphen | mountain- top | the joined form is printed nowhere else |
| DBT | Isa 29:14 | split | under standing | both halves are words |
| DBT | Isa 49:23 | hyphen | nursing -fathers, | the joined form is printed nowhere else |
| DBT | Isa 49:23 | hyphen | nursing- mothers: | the joined form is printed nowhere else |
| DBT | Jer 1:17 | split | a rise, | both halves are words |
| DBT | Jer 19:2 | hyphen | pottery- gate, | the joined form is printed nowhere else |
| DBT | Jer 28:11 | split | with in | both halves are words |
| DBT | Jer 41:17 | hyphen | Geruth -Chimham, | the joined form is printed nowhere else |
| DBT | Jer 48:34 | hyphen | Eglath- shelishijah: | the joined form is printed nowhere else |
| DBT | Lam 2:11 | split | up on | both halves are words |
| DBT | Ezek 8:6 | split | a gain | both halves are words |
| DBT | Ezek 9:2 | hyphen | ink- horn | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| DBT | Ezek 9:3 | hyphen | ink- horn | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| DBT | Ezek 9:11 | hyphen | ink -horn | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| DBT | Ezek 11:21 | hyphen | well -pleased | the joined form is printed nowhere else |
| DBT | Ezek 13:11 | split | hail stones, | both halves are words |
| DBT | Ezek 21:22 | hyphen | siege -towers. | the joined form is printed nowhere else |
| DBT | Ezek 41:24 | hyphen | turning- leaves: | the joined form is printed nowhere else |
| DBT | Ezek 46:11 | hyphen | feast -days, | the joined form is printed nowhere else |
| DBT | Ezek 46:13 | hyphen | yearling -lamb | the joined form is printed nowhere else |
| DBT | Dan 11:15 | hyphen | well -fenced | the joined form is printed nowhere else |
| DBT | Hos 10:15 | hyphen | day- break | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| DBT | Mic 7:1 | hyphen | summer -fruits, | the joined form is printed nowhere else |
| DBT | Hag 2:15 | hyphen | press -measures, | the joined form is printed nowhere else |
| DBT | Zech 9:10 | hyphen | battle -bow | the joined form is printed nowhere else |
| DBT | Matt 4:13 | hyphen | sea -side | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| DBT | Matt 16:17 | hyphen | Bar -jona, | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| DBT | Matt 27:7 | hyphen | burying- ground | the joined form is printed nowhere else |
| DBT | Mark 10:5 | hyphen | hard- heartedness | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| DBT | Mark 13:35 | hyphen | cock- crow, | the joined form is printed nowhere else |
| DBT | Mark 15:21 | hyphen | passer -by, | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| DBT | Luke 4:35 | split | say ing, | both halves are words |
| DBT | Luke 9:7 | split | he ard | both halves are words |
| DBT | Luke 11:33 | hyphen | corn- measure, | the joined form is printed nowhere else |
| DBT | John 2:6 | hyphen | water -vessels, | the joined form is printed nowhere else |
| DBT | John 2:7 | hyphen | water -vessels | the joined form is printed nowhere else |
| DBT | Acts 13:1 | hyphen | foster -brother | the joined form is printed nowhere else |
| DBT | Acts 18:3 | hyphen | tent -makers | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| DBT | Acts 19:24 | hyphen | silver -beater, | the joined form is printed nowhere else |
| DBT | Acts 23:23 | hyphen | light -armed | the joined form is printed nowhere else |
| DBT | Rom 9:4 | hyphen | law -giving, | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| DBT | Rom 11:2 | split | Eli as, | both halves are words |
| DBT | Rom 16:7 | hyphen | fellow -captives, | the joined form is printed nowhere else |
| DBT | 1 Cor 8:10 | hyphen | idol -house, | the joined form is printed nowhere else |
| DBT | 2 Cor 8:19 | hyphen | fellow -traveller | the joined form is printed nowhere else |
| DBT | Eph 1:13 | split | gl ad | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| DBT | Eph 3:10 | hyphen | all -various | the joined form is printed nowhere else |
| DBT | Eph 4:13 | hyphen | full -grown | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| DBT | Phil 1:7 | split | be cause | both halves are words |
| DBT | Phil 2:6 | split | es teem | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| DBT | 1 Tim 5:6 | hyphen | self- indulgence | the joined form is printed nowhere else |
| DBT | 1 Tim 6:20 | hyphen | false- named | the joined form is printed nowhere else |
| DBT | Heb 5:14 | hyphen | full -grown | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| DBT | Heb 6:9 | split | be loved, | both halves are words |
| DBT | Heb 13:3 | hyphen | evil -treated, | the joined form is printed nowhere else |
| DBT | Jas 3:8 | hyphen | death- bringing | the joined form is printed nowhere else |
| DBT | 1 Pet 3:7 | hyphen | fellow -heirs | the joined form is printed nowhere else |
| DBT | 1 Pet 3:17 | hyphen | well -doers | the joined form is printed nowhere else |
| DBT | 2 Pet 1:9 | hyphen | short -sighted, | the joined form is printed nowhere else |
| DBT | 1 John 1:2 | split | re port | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| DRB | Gen 9:15 | split | re member | both halves are words |
| DRB | Gen 10:32 | split | we re | both halves are words |
| DRB | Gen 16:5 | split | hand maid | both halves are words |
| DRB | Gen 17:11 | split | a h | a one-letter word, and the joined word is not attested beside its neighbours |
| DRB | Gen 19:2 | split | in to | both halves are words |
| DRB | Gen 20:5 | split | he art, | both halves are words |
| DRB | Gen 20:18 | hyphen | ac- count | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| DRB | Gen 29:10 | hyphen | cousin -german, | the joined form is printed nowhere else |
| DRB | Gen 30:43 | split | maid servants | both halves are words |
| DRB | Gen 38:10 | hyphen | be- cause | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| DRB | Gen 40:8 | split | n obody | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| DRB | Gen 41:51 | split | first born | both halves are words |
| DRB | Gen 42:28 | glued | hehold | no sibling prints the two words |
| DRB | Gen 45:20 | hyphen | house- hold | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| DRB | Gen 46:16 | glued | Heri | no sibling prints the two words |
| DRB | Gen 46:21 | glued | Ared | printed as a compound or the translation's own spelling, not two words |
| DRB | Gen 46:22 | hyphen | four- teen. | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| DRB | Gen 47:23 | hyphen | Be- hold | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| DRB | Gen 48:21 | hyphen | Be- hold | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| DRB | Gen 49:6 | hyphen | “be- cause | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| DRB | Gen 49:16 | hyphen | an- other | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| DRB | Gen 49:30 | hyphen | to- gather | the joined form is printed nowhere else |
| DRB | Gen 50:11 | hyphen | there- fore | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| DRB | Exod 4:25 | split | fore skin | both halves are words |
| DRB | Exod 10:4 | split | in to | both halves are words |
| DRB | Exod 20:12 | glued | longlived | printed as a compound or the translation's own spelling, not two words |
| DRB | Exod 26:20 | split | th at | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| DRB | Lev 11:32 | split | uncle an | both halves are words |
| DRB | Lev 14:36 | hyphen | after- wards | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| DRB | Lev 26:35 | split | be cause | both halves are words |
| DRB | Num 5:15 | hyphen | frank- incense | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| DRB | Num 10:9 | split | deliver ed | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| DRB | Num 12:14 | split | after wards | both halves are words |
| DRB | Num 13:9 | split | P halti | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| DRB | Num 35:20 | hyphen | thing- at | the joined form is printed nowhere else |
| DRB | Deut 3:5 | hyphen | be- sides | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| DRB | Deut 3:21 | hyphen | king- dome | the joined form is printed nowhere else |
| DRB | Deut 7:1 | split | in to | both halves are words |
| DRB | Deut 28:22 | hyphen | miser- able | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| DRB | Deut 31:12 | split | str angers, | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| DRB | Deut 31:15 | split | en try | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| DRB | Deut 31:16 | split | in to | both halves are words |
| DRB | Josh 15:6 | hyphen | Beth -Araba: | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| DRB | Josh 15:6 | hyphen | Beth -Hagla, | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| DRB | Josh 20:7 | hyphen | th- Arbe, | the joined form is printed nowhere else |
| DRB | Josh 24:32 | split | fat her | both halves are words |
| DRB | Judg 19:29 | split | in to | both halves are words |
| DRB | Judg 20:33 | split | whe re | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| DRB | 1 Sam 1:19 | split | re turned, | both halves are words |
| DRB | 1 Sam 19:21 | split | al so. | both halves are words |
| DRB | 1 Sam 28:19 | split | al so | both halves are words |
| DRB | 2 Sam 3:8 | split | in to | both halves are words |
| DRB | 2 Sam 4:5 | split | com ing, | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| DRB | 2 Sam 6:10 | split | ca used | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| DRB | 2 Sam 6:10 | split | in to | both halves are words |
| DRB | 2 Sam 12:30 | split | we re | both halves are words |
| DRB | 2 Sam 13:9 | split | per sons | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| DRB | 2 Sam 19:41 | split | house hold | both halves are words |
| DRB | 1 Kgs 1:28 | split | in to | both halves are words |
| DRB | 1 Kgs 4:10 | hyphen | Nephath -Dor, | the joined form is printed nowhere else |
| DRB | 1 Kgs 7:5 | hyphen | in- all | the joined form is printed nowhere else |
| DRB | 1 Kgs 7:45 | hyphen | Hi- ram | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| DRB | 1 Kgs 8:34 | hyphen | for- give | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| DRB | 1 Kgs 14:13 | hyphen | be- cause | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| DRB | 1 Kgs 22:19 | split | there fore | both halves are words |
| DRB | 2 Kgs 3:22 | split | up on | both halves are words |
| DRB | 2 Kgs 4:11 | split | in to | both halves are words |
| DRB | 2 Kgs 5:20 | split | some thing | both halves are words |
| DRB | 2 Kgs 7:2 | hyphen | hood -gates | the joined form is printed nowhere else |
| DRB | 2 Kgs 8:21 | glued | Seira | no sibling prints the two words |
| DRB | 2 Kgs 9:16 | split | the re, | both halves are words |
| DRB | 2 Kgs 11:4 | split | in to | both halves are words |
| DRB | 2 Kgs 14:28 | hyphen | where- with | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| DRB | 2 Kgs 19:36 | hyphen | re- turned | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| DRB | 2 Kgs 21:2 | split | be fore | both halves are words |
| DRB | 2 Kgs 25:25 | split | Mas pha. | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| DRB | 1 Chr 3:11 | hyphen | be- got | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| DRB | 1 Chr 4:36 | glued | Jacoba | no sibling prints the two words |
| DRB | 1 Chr 11:26 | glued | Asahe | no sibling prints the two words |
| DRB | 1 Chr 20:6 | split | Ge th, | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| DRB | 1 Chr 22:18 | hyphen | be- fore | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| DRB | 1 Chr 25:6 | split | we re | both halves are words |
| DRB | 1 Chr 28:9 | hyphen | under- standeth | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| DRB | 1 Chr 28:14 | hyphen | ac- cording | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| DRB | 2 Chr 1:6 | split | up on | both halves are words |
| DRB | 2 Chr 2:2 | hyphen | over- see | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| DRB | 2 Chr 4:4 | hyphen | in- ward | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| DRB | 2 Chr 13:3 | hyphen | thou- sand | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| DRB | 2 Chr 15:12 | split | in to | both halves are words |
| DRB | 2 Chr 23:12 | split | in to | both halves are words |
| DRB | 2 Chr 25:9 | glued | Israeli | no sibling prints the two words |
| DRB | 2 Chr 27:6 | hyphen | be- cause | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| DRB | 2 Chr 28:9 | hyphen | Be- hold | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| DRB | 2 Chr 34:22 | glued | Olda | no sibling prints the two words |
| DRB | Ezra 1:4 | glued | restin | no sibling prints the two words |
| DRB | Ezra 2:16 | glued | Ather | no sibling prints the two words |
| DRB | Ezra 3:2 | split | Salathi el, | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| DRB | Neh 1:10 | split | a re | both halves are words |
| DRB | Neh 5:3 | hyphen | be- cause | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| DRB | Neh 7:64 | hyphen | re- cord, | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| DRB | Neh 9:19 | split | de parted | both halves are words |
| DRB | Neh 9:25 | hyphen | de- light | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| DRB | Neh 9:25 | hyphen | vine- yards, | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| DRB | Neh 12:24 | hyphen | ac- cording | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| DRB | Neh 13:1 | split | in to | both halves are words |
| DRB | Esth 1:6 | split | up on | both halves are words |
| DRB | Ps 35:14 | split | a n | a one-letter word, and the joined word is not attested beside its neighbours |
| DRB | Ps 89:7 | split | a re | both halves are words |
| DRB | Ps 119:165 | split | stumbling block | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| DRB | Prov 5:13 | hyphen | in- dined | the joined form is printed nowhere else |
| DRB | Prov 13:23 | split | with out | both halves are words |
| DRB | Prov 20:30 | hyphen | in- ward | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| DRB | Prov 21:5 | hyphen | al- ways | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| DRB | Prov 22:16 | hyphen | in- crease | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| DRB | Isa 10:10 | hyphen | king- dome | the joined form is printed nowhere else |
| DRB | Isa 19:21 | hyphen | per- form | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| DRB | Isa 24:5 | hyphen | in- habitants | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| DRB | Isa 28:20 | hyphen | can- not | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| DRB | Isa 30:3 | hyphen | the- strength | the joined form is printed nowhere else |
| DRB | Isa 43:21 | hyphen | my- self, | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| DRB | Isa 45:17 | hyphen | con- founded, | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| DRB | Isa 47:14 | hyphen | them- selves | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| DRB | Jer 29:26 | hyphen | in- stead | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| DRB | Jer 45:1 | split | ye ar | both halves are words |
| DRB | Jer 49:4 | split | ha st | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| DRB | Ezek 32:30 | hyphen | con- founded | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| DRB | Ezek 44:25 | split | the ir | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| DRB | Dan 11:39 | split | th is | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| DRB | Hos 2:7 | split | hus band, | both halves are words |
| DRB | Hos 12:8 | hyphen | be- come | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| DRB | Hos 12:13 | hyphen | pre- served | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| DRB | Amos 4:2 | split | up on | both halves are words |
| DRB | Obad 1:20 | hyphen | Bospho- rus, | the joined form is printed nowhere else |
| DRB | Zech 4:7 | split | mount ain, | both halves are words |
| DRB | Zech 6:4 | hyphen | an- gel | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| DRB | Zech 14:12 | split | where with | both halves are words |
| DRB | Matt 14:26 | split | se a, | both halves are words |
| DRB | Matt 16:17 | hyphen | Bar -Jona: | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| DRB | Matt 17:3 | split | Eli as | both halves are words |
| DRB | Matt 20:3 | split | market place | both halves are words |
| DRB | Matt 21:24 | split | the se | both halves are words |
| DRB | Mark 13:25 | split | a re | both halves are words |
| DRB | Mark 15:12 | split | a gain | both halves are words |
| DRB | Luke 13:17 | split | we re | both halves are words |
| DRB | Luke 24:21 | split | be sides | both halves are words |
| DRB | John 15:14 | split | th at | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| DRB | Acts 5:33 | split | he art, | both halves are words |
| DRB | Acts 12:25 | split | re turned | both halves are words |
| DRB | Acts 13:16 | glued | bespeaking | no sibling prints the two words |
| DRB | Acts 15:25 | split | be loved | both halves are words |
| DRB | Acts 23:17 | split | some thing | both halves are words |
| DRB | Acts 23:18 | split | some thing | both halves are words |
| DRB | Acts 23:20 | split | some thing | both halves are words |
| DRB | Acts 27:8 | hyphen | Good- havens, | the joined form is printed nowhere else |
| DRB | Rom 4:6 | split | just ice | both halves are words |
| DRB | Rom 5:8 | split | a ccording | a one-letter word, and the joined word is not attested beside its neighbours |
| DRB | Gal 2:6 | split | some thing | both halves are words |
| DRB | Gal 2:6 | split | some thing, | both halves are words |
| DRB | Gal 6:3 | split | some thing, | both halves are words |
| DRB | Eph 1:10 | hyphen | re- establish | the joined form is printed nowhere else |
| DRB | Phil 1:18 | split | a ll | a one-letter word, and the joined word is not attested beside its neighbours |
| DRB | Phil 2:7 | split | in habit | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| DRB | Phil 3:12 | split | a ttained, | a one-letter word, and the joined word is not attested beside its neighbours |
| DRB | Col 1:19 | split | Fat her, | both halves are words |
| DRB | Col 1:21 | split | a lienated | a one-letter word, and the joined word is not attested beside its neighbours |
| DRB | Col 3:18 | split | be hoveth | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| DRB | 1 Thess 2:15 | split | a re | both halves are words |
| DRB | 2 Thess 2:4 | split | sit teth | both halves are words |
| DRB | 2 Tim 1:15 | split | a re | both halves are words |
| DRB | 2 Tim 2:13 | split | can not | both halves are words |
| DRB | Titus 2:8 | split | can not | both halves are words |
| DRB | Heb 4:15 | split | can not | both halves are words |
| DRB | Heb 8:3 | split | some thing | both halves are words |
| DRB | Heb 9:9 | split | can not, | both halves are words |
| DRB | Jas 2:22 | hyphen | co -operate | the joined form is printed nowhere else |
| DRB | Jas 4:2 | split | can not | both halves are words |
| DRB | 1 John 3:9 | split | can not | both halves are words |
| DRB | 1 John 5:16 | split | The re | both halves are words |
| DRB | Rev 13:2 | split | we re | both halves are words |
| DRB | Rev 16:17 | split | the re | both halves are words |
| ERV | Gen 27:7 | split | me at, | both halves are words |
| ERV | Gen 31:51 | split | be hold | both halves are words |
| ERV | Exod 9:22 | split | to ward | both halves are words |
| ERV | Exod 20:7 | split | guilt less | both halves are words |
| ERV | Num 24:6 | hyphen | lign -aloes | the joined form is printed nowhere else |
| ERV | Deut 9:13 | split | be hold, | both halves are words |
| ERV | Josh 15:27 | hyphen | Hasar- gaddah, | the joined form is printed nowhere else |
| ERV | Josh 15:53 | hyphen | Bath -tappuah, | the joined form is printed nowhere else |
| ERV | 1 Sam 19:4 | hyphen | thee -ward | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| ERV | 1 Sam 26:19 | split | stir red | both halves are words |
| ERV | 2 Sam 15:17 | hyphen | Beth- merhak. | the joined form is printed nowhere else |
| ERV | 2 Sam 18:18 | split | life time | both halves are words |
| ERV | 1 Kgs 3:21 | split | be hold, | both halves are words |
| ERV | 1 Kgs 7:26 | split | flow er | both halves are words |
| ERV | 1 Chr 25:4 | split | a nd | a one-letter word, and the joined word is not attested beside its neighbours |
| ERV | 2 Chr 2:18 | glued | awork | printed as a compound or the translation's own spelling, not two words |
| ERV | 2 Chr 6:30 | split | he art | both halves are words |
| ERV | Ezra 5:3 | hyphen | Shethar -bonzenai, | the joined form is printed nowhere else |
| ERV | Ezra 10:21 | split | Shem aiah, | both halves are words |
| ERV | Neh 9:17 | split | bond age: | both halves are words |
| ERV | Job 37:23 | split | can not | both halves are words |
| ERV | Ps 22:1 | hyphen | hash- Shahar. | the joined form is printed nowhere else |
| ERV | Ps 55:21 | split | he art | both halves are words |
| ERV | Ps 109:21 | split | be cause | both halves are words |
| ERV | Isa 3:8 | split | be cause | both halves are words |
| ERV | Isa 26:7 | split | up right | both halves are words |
| ERV | Isa 33:17 | split | a far | both halves are words |
| ERV | Isa 48:2 | split | them selves | both halves are words |
| ERV | Jer 23:15 | split | Be hold, | both halves are words |
| ERV | Jer 28:3 | split | a gain | both halves are words |
| ERV | Jer 46:2 | hyphen | Pharaoh -neco, | the joined form is printed nowhere else |
| ERV | Ezek 23:4 | split | be came | both halves are words |
| ERV | Ezek 41:17 | split | a bout | a one-letter word beside a word printed elsewhere |
| ERV | Hos 1:1 | split | Hose a | a one-letter word beside a word printed elsewhere |
| ERV | Hos 1:6 | split | a gain, | both halves are words |
| ERV | Hab 2:5 | split | a s | a one-letter word, and the joined word is not attested beside its neighbours |
| ERV | Matt 16:17 | hyphen | Bar -Jonah: | the joined form is printed nowhere else |
| ERV | Matt 19:9 | split | an other, | both halves are words |
| ERV | Acts 1:15 | split | a bout | a one-letter word beside a word printed elsewhere |
| ERV | Acts 10:7 | hyphen | household- servants, | the joined form is printed nowhere else |
| ERV | Acts 13:1 | hyphen | foster -brother | the joined form is printed nowhere else |
| ERV | Acts 23:34 | split | under stood | both halves are words |
| ERV | Acts 25:11 | hyphen | wrong- doer, | the joined form is printed nowhere else |
| ERV | Acts 27:17 | hyphen | under -girding | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| ERV | Rom 1:31 | hyphen | covenant -breakers, | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| ERV | 2 Cor 10:8 | split | a bundantly | a one-letter word, and the joined word is not attested beside its neighbours |
| ERV | Eph 3:3 | split | a fore | a one-letter word beside a word printed elsewhere |
| JPS | Gen 6:16 | split | low er, | both halves are words |
| JPS | Gen 14:7 | hyphen | En -mishpat—the | the joined form is printed nowhere else |
| JPS | Gen 22:14 | hyphen | Adonai -jireh; | the joined form is printed nowhere else |
| JPS | Gen 25:31 | split | birth right.’ | both halves are words |
| JPS | Gen 32:32 | hyphen | thigh- vein | the joined form is printed nowhere else |
| JPS | Gen 32:32 | hyphen | thigh- vein. | the joined form is printed nowhere else |
| JPS | Gen 35:17 | hyphen | mid- wife | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| JPS | Exod 16:14 | hyphen | scale -like | the joined form is printed nowhere else |
| JPS | Exod 20:18 | split | a far | both halves are words |
| JPS | Exod 25:32 | hyphen | candle -stick | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| JPS | Exod 25:32 | split | there of: | both halves are words |
| JPS | Lev 3:9 | hyphen | rump- bone; | the joined form is printed nowhere else |
| JPS | Lev 6:9 | split | up on | both halves are words |
| JPS | Lev 7:8 | split | him self | both halves are words |
| JPS | Num 8:21 | split | wash ed | both halves are words |
| JPS | Num 9:13 | split | pass over, | both halves are words |
| JPS | Num 14:3 | split | re turn | both halves are words |
| JPS | Num 18:16 | hyphen | redemption- money—from | the joined form is printed nowhere else |
| JPS | Num 19:15 | hyphen | close- bound | the joined form is printed nowhere else |
| JPS | Num 22:5 | split | the re | both halves are words |
| JPS | Num 22:36 | hyphen | Ir -moab, | the joined form is printed nowhere else |
| JPS | Deut 5:10 | split | thousa ndth | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| JPS | Deut 10:6 | hyphen | Beeroth- benejaakan | the joined form is printed nowhere else |
| JPS | Deut 14:21 | split | wit hin | both halves are words |
| JPS | Deut 18:10 | split | a s | a one-letter word, and the joined word is not attested beside its neighbours |
| JPS | Deut 23:8 | split | a re | both halves are words |
| JPS | Deut 24:2 | split | become th | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| JPS | Deut 32:17 | hyphen | no- gods, | the joined form is printed nowhere else |
| JPS | Deut 32:21 | hyphen | no- god; | the joined form is printed nowhere else |
| JPS | Josh 9:4 | split | wine skins, | both halves are words |
| JPS | Josh 16:6 | hyphen | Mich- methath | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| JPS | Josh 17:16 | hyphen | eth- shean | the joined form is printed nowhere else |
| JPS | Josh 18:14 | split | a bout | a one-letter word beside a word printed elsewhere |
| JPS | Josh 19:33 | hyphen | Elon -beza-anannim, | the joined form is printed nowhere else |
| JPS | Josh 19:35 | hyphen | Ziddim -zer, | the joined form is printed nowhere else |
| JPS | Judg 1:10 | hyphen | Kiriath- arba—and | the joined form is printed nowhere else |
| JPS | Judg 7:1 | hyphen | Gibeath -moreh, | the joined form is printed nowhere else |
| JPS | Judg 20:10 | split | thou sand | both halves are words |
| JPS | 1 Sam 1:22 | split | the re | both halves are words |
| JPS | 1 Sam 13:16 | split | pre sent | both halves are words |
| JPS | 1 Sam 17:15 | hyphen | Beth- lehem.— | the joined form is printed nowhere else |
| JPS | 1 Sam 25:11 | split | a re?’ | both halves are words |
| JPS | 2 Sam 18:10 | split | A bsalom | a one-letter word, and the joined word is not attested beside its neighbours |
| JPS | 2 Sam 23:30 | hyphen | Nahale -gaash; | the joined form is printed nowhere else |
| JPS | 1 Kgs 2:22 | split | moth er: | both halves are words |
| JPS | 1 Kgs 15:28 | split | ye ar | both halves are words |
| JPS | 2 Kgs 2:2 | hyphen | Beth -el.— | the joined form is printed nowhere else |
| JPS | 2 Kgs 20:10 | split | answer ed: | both halves are words |
| JPS | 2 Kgs 21:8 | split | fat hers; | both halves are words |
| JPS | 1 Chr 2:24 | hyphen | Caleb- ephrath, | the joined form is printed nowhere else |
| JPS | 1 Chr 4:11 | split | fat her | both halves are words |
| JPS | 1 Chr 7:18 | hyphen | Ish -hod, | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| JPS | 1 Chr 11:32 | hyphen | Nahale -gaash, | the joined form is printed nowhere else |
| JPS | 2 Chr 6:14 | split | the re | both halves are words |
| JPS | 2 Chr 6:42 | split | anoint ed; | both halves are words |
| JPS | 2 Chr 20:2 | hyphen | Hazazon- tamar’—the | the joined form is printed nowhere else |
| JPS | 2 Chr 23:18 | split | dire ction | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| JPS | 2 Chr 29:15 | split | ho use | both halves are words |
| JPS | 2 Chr 29:24 | split | a s | a one-letter word, and the joined word is not attested beside its neighbours |
| JPS | Ezra 8:31 | hyphen | lier -in-wait | the joined form is printed nowhere else |
| JPS | Neh 6:8 | split | ‘The re | both halves are words |
| JPS | Neh 9:15 | split | the ir | both halves are words |
| JPS | Neh 11:17 | split | thanks giving | both halves are words |
| JPS | Esth 2:9 | split | ho use | both halves are words |
| JPS | Ps 9:15 | split | the ir | both halves are words |
| JPS | Ps 35:3 | hyphen | battle -axe, | the joined form is printed nowhere else |
| JPS | Ps 35:15 | split | gat her | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| JPS | Ps 39:4 | hyphen | short- lived | the joined form is printed nowhere else |
| JPS | Ps 56:1 | hyphen | Jonath- elem-rehokim. | the joined form is printed nowhere else |
| JPS | Ps 74:4 | hyphen | meeting- place; | the joined form is printed nowhere else |
| JPS | Eccl 8:5 | split | he art | both halves are words |
| JPS | Isa 7:19 | split | up on | both halves are words |
| JPS | Isa 8:3 | hyphen | Maher -shalal-hashbaz. | the joined form is printed nowhere else |
| JPS | Isa 28:14 | hyphen | ballad- mongers | the joined form is printed nowhere else |
| JPS | Isa 29:13 | hyphen | command- ment | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| JPS | Isa 38:8 | hyphen | sun- dial | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| JPS | Isa 65:13 | split | Be hold, | both halves are words |
| JPS | Isa 66:3 | split | the ir | both halves are words |
| JPS | Jer 5:7 | hyphen | no -gods; | the joined form is printed nowhere else |
| JPS | Jer 37:16 | hyphen | dungeon- house, | the joined form is printed nowhere else |
| JPS | Jer 46:2 | hyphen | Pharaoh -neco | the joined form is printed nowhere else |
| JPS | Jer 51:31 | split | an other, | both halves are words |
| JPS | Ezek 27:24 | hyphen | cedar -lined, | the joined form is printed nowhere else |
| JPS | Ezek 28:14 | hyphen | far -covering | the joined form is printed nowhere else |
| JPS | Ezek 47:19 | hyphen | Meriboth -kadesh, | the joined form is printed nowhere else |
| JPS | Hos 1:2 | split | Hose a: | a one-letter word beside a word printed elsewhere |
| JPS | Hos 5:4 | split | wit hin | both halves are words |
| JPS | Hos 13:15 | hyphen | reed- plants, | the joined form is printed nowhere else |
| JPS | Nah 2:10 | split | he art | both halves are words |
| JPS | Hag 2:16 | hyphen | press- measures, | the joined form is printed nowhere else |
| JPS | Zech 13:5 | split | a t | a one-letter word, and the joined word is not attested beside its neighbours |
| JPS | Matt 1:21 | split | the ir | both halves are words |
| JPS | Matt 6:20 | hyphen | wear -and-tear | the joined form is printed nowhere else |
| JPS | Matt 13:30 | hyphen | harvest -time | the joined form is printed nowhere else |
| JPS | Matt 13:31 | hyphen | tard- seed, | the joined form is printed nowhere else |
| JPS | Matt 13:41 | split | commis sion | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| JPS | Matt 24:13 | split | st and | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| JPS | Matt 27:33 | hyphen | ‘Skull -ground.’ | the joined form is printed nowhere else |
| JPS | Mark 5:21 | hyphen | re- crossed | the joined form is printed nowhere else |
| JPS | Mark 6:30 | hyphen | re -assembled | the joined form is printed nowhere else |
| JPS | Mark 9:47 | hyphen | half- blind | the joined form is printed nowhere else |
| JPS | Mark 9:47 | split | in to | both halves are words |
| JPS | Mark 9:50 | split | th ing, | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| JPS | Mark 12:1 | hyphen | wine -tank, | the joined form is printed nowhere else |
| JPS | Mark 13:35 | hyphen | cock -crow, | the joined form is printed nowhere else |
| JPS | Mark 14:28 | hyphen | to- day—this | the joined form is printed nowhere else |
| JPS | Mark 14:67 | split | look ed | both halves are words |
| JPS | Mark 15:22 | hyphen | ‘Skull -ground.’ | the joined form is printed nowhere else |
| JPS | Mark 15:37 | split | utter ed | both halves are words |
| JPS | Luke 1:63 | hyphen | writing- tablet, | the joined form is printed nowhere else |
| JPS | Luke 9:57 | hyphen | good- bye | the joined form is printed nowhere else |
| JPS | Luke 10:17 | hyphen | lightning- flash | the joined form is printed nowhere else |
| JPS | Luke 22:68 | split | questio ns, | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| JPS | John 3:26 | split | be en | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| JPS | John 7:2 | hyphen | Tent -Pitching | the joined form is printed nowhere else |
| JPS | John 11:19 | split | de ath | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| JPS | John 11:52 | hyphen | far -scattered | the joined form is printed nowhere else |
| JPS | John 12:6 | hyphen | money- box, | the joined form is printed nowhere else |
| JPS | John 13:29 | hyphen | money -box | the joined form is printed nowhere else |
| JPS | John 19:8 | hyphen | re -entered | the joined form is printed nowhere else |
| JPS | John 19:17 | hyphen | Skull -place—or, | the joined form is printed nowhere else |
| JPS | Acts 2:13 | hyphen | brim -full | the joined form is printed nowhere else |
| JPS | Acts 2:46 | hyphen | single -heartedness, | the joined form is printed nowhere else |
| JPS | Acts 4:6 | hyphen | high -priestly | the joined form is printed nowhere else |
| JPS | Acts 4:36 | hyphen | Bar -nabas—signifying | the joined form is printed nowhere else |
| JPS | Acts 6:1 | hyphen | Greek- speaking | the joined form is printed nowhere else |
| JPS | Acts 6:9 | hyphen | Freed- men,’ | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| JPS | Acts 13:1 | hyphen | foster -brother) | the joined form is printed nowhere else |
| JPS | Acts 13:10 | split | craft iness | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| JPS | Acts 13:45 | split | op posed | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| JPS | Acts 19:14 | hyphen | high -priestly | the joined form is printed nowhere else |
| JPS | Acts 19:16 | hyphen | over -mastered | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| JPS | Acts 19:40 | hyphen | to- day’s | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| JPS | Acts 21:15 | hyphen | baggage -cattle | the joined form is printed nowhere else |
| JPS | Acts 21:21 | hyphen | old -established | the joined form is printed nowhere else |
| JPS | Acts 21:37 | hyphen | cut -throats, | the joined form is printed nowhere else |
| JPS | Acts 22:23 | split | the ir | both halves are words |
| JPS | Acts 27:17 | hyphen | frapping- cables | the joined form is printed nowhere else |
| JPS | Acts 28:2 | hyphen | strange- speaking | the joined form is printed nowhere else |
| JPS | Rom 1:14 | hyphen | Greek- speaking | the joined form is printed nowhere else |
| JPS | Rom 2:7 | hyphen | right -doing, | the joined form is printed nowhere else |
| JPS | Rom 6:19 | hyphen | ever -increasing | the joined form is printed nowhere else |
| JPS | Rom 8:7 | split | st ate | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| JPS | Rom 8:14 | split | a re, | both halves are words |
| JPS | Rom 9:22 | hyphen | long- forbearing | the joined form is printed nowhere else |
| JPS | Rom 9:33 | split | ha ve | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| JPS | Rom 15:9 | split | writ ten, | both halves are words |
| JPS | 1 Cor 2:10 | split | te aching | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| JPS | 1 Cor 7:16 | split | ha ve | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| JPS | 1 Cor 10:30 | split | grat eful | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| JPS | 2 Cor 3:1 | hyphen | self- recommendation | the joined form is printed nowhere else |
| JPS | 2 Cor 10:1 | hyphen | self -forgetfulness | the joined form is printed nowhere else |
| JPS | 2 Cor 10:12 | hyphen | self- commendation. | the joined form is printed nowhere else |
| JPS | 2 Cor 11:3 | hyphen | single -heartedness | the joined form is printed nowhere else |
| JPS | 2 Cor 11:21 | hyphen | self- disparagement, | the joined form is printed nowhere else |
| JPS | Gal 1:10 | hyphen | man- pleaser, | the joined form is printed nowhere else |
| JPS | Gal 4:30 | hyphen | slave -girl’s | the joined form is printed nowhere else |
| JPS | Eph 4:13 | hyphen | full -grown | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| JPS | Eph 5:5 | hyphen | idol -worshipper—has | the joined form is printed nowhere else |
| JPS | Eph 5:5 | hyphen | money- grubber—or | the joined form is printed nowhere else |
| JPS | Phil 1:19 | split | bou ntiful | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| JPS | Phil 2:1 | hyphen | tender -heartedness | the joined form is printed nowhere else |
| JPS | Phil 2:10 | split | He aven, | both halves are words |
| JPS | Phil 3:2 | hyphen | self- mutilators. | the joined form is printed nowhere else |
| JPS | Col 2:2 | split | enjoyi ng | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| JPS | Col 2:20 | split | ot her | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| JPS | Col 3:12 | hyphen | tender -heartedness, | the joined form is printed nowhere else |
| JPS | 1 Thess 5:3 | hyphen | birth- pains | the joined form is printed nowhere else |
| JPS | 2 Thess 3:2 | hyphen | wrong- headed | the joined form is printed nowhere else |
| JPS | 1 Tim 4:10 | split | wrest ling, | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| JPS | 2 Tim 2:23 | glued | knowi | no sibling prints the two words |
| JPS | 2 Tim 3:4 | hyphen | self- important. | the joined form is printed nowhere else |
| JPS | Titus 2:3 | hyphen | wine -drinking. | the joined form is printed nowhere else |
| JPS | Heb 1:3 | hyphen | all -powerful | the joined form is printed nowhere else |
| JPS | Heb 2:15 | glued | lifelong | no sibling prints the two words |
| JPS | Heb 6:1 | hyphen | re -laying | the joined form is printed nowhere else |
| JPS | Heb 7:4 | hyphen | priest -king | the joined form is printed nowhere else |
| JPS | Heb 10:29 | hyphen | Covenant -blood | the joined form is printed nowhere else |
| JPS | Heb 11:15 | split | che rished | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| JPS | Heb 11:25 | hyphen | short -lived | the joined form is printed nowhere else |
| JPS | Jas 2:22 | hyphen | co- operating | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| JPS | Jas 3:8 | hyphen | ever -busy | the joined form is printed nowhere else |
| JPS | Jas 4:16 | hyphen | self -confidence | the joined form is printed nowhere else |
| JPS | 1 Pet 2:2 | hyphen | newly- born | the joined form is printed nowhere else |
| JPS | 1 Pet 3:10 | hyphen | well -satisfied | the joined form is printed nowhere else |
| JPS | 2 Pet 1:19 | hyphen | dimly- lighted | the joined form is printed nowhere else |
| JPS | 2 Pet 3:16 | hyphen | ill -taught | the joined form is printed nowhere else |
| JPS | 1 John 3:9 | hyphen | God -given | the joined form is printed nowhere else |
| JPS | Rev 5:5 | split | be longs | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| JPS | Rev 7:9 | hyphen | palm -branches | the joined form is printed nowhere else |
| JPS | Rev 9:17 | hyphen | body -armour | the joined form is printed nowhere else |
| JPS | Rev 12:4 | split | a bout | a one-letter word beside a word printed elsewhere |
| JPS | Rev 13:6 | hyphen | dwelling- place—that | the joined form is printed nowhere else |
| JPS | Rev 13:14 | split | e rect | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| JPS | Rev 16:19 | hyphen | wine -cup | the joined form is printed nowhere else |
| JPS | Rev 17:7 | hyphen | re -ascend, | the joined form is printed nowhere else |
| JPS | Rev 17:17 | split | ha ve | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| JPS | Rev 19:1 | hyphen | far -echoing | the joined form is printed nowhere else |
| JPS | Rev 21:15 | hyphen | measuring -rod | the joined form is printed nowhere else |
| JPS | Rev 21:19 | hyphen | foundation -stones | the joined form is printed nowhere else |
| JPS | Rev 22:9 | split | fulfill ment | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| KJV | Gen 34:26 | split | ho use, | both halves are words |
| KJV | Exod 32:29 | split | up on | both halves are words |
| KJV | Lev 13:48 | split | whet her | both halves are words |
| KJV | Num 1:40 | split | fat hers, | both halves are words |
| KJV | Josh 2:19 | split | in to | both halves are words |
| KJV | Josh 14:12 | split | mount ain, | both halves are words |
| KJV | Judg 15:1 | split | a fter, | a one-letter word, and the joined word is not attested beside its neighbours |
| KJV | 2 Sam 17:19 | split | there on; | both halves are words |
| KJV | 2 Sam 21:8 | split | Ai ah, | both halves are words |
| KJV | 1 Kgs 19:20 | split | a gain: | both halves are words |
| KJV | 1 Chr 25:4 | split | He man; | both halves are words |
| KJV | 2 Chr 9:13 | split | ye ar | both halves are words |
| KJV | 2 Chr 16:3 | split | be hold, | both halves are words |
| KJV | 2 Chr 25:2 | split | he art. | both halves are words |
| KJV | Neh 3:8 | split | Hanani ah | both halves are words |
| KJV | Neh 9:37 | split | be cause | both halves are words |
| KJV | Isa 22:7 | split | horse men | both halves are words |
| KJV | Isa 47:13 | split | a strologers, | a one-letter word beside a word printed elsewhere |
| KJV | Jer 2:32 | split | for gotten | both halves are words |
| KJV | Jer 36:12 | split | in to | both halves are words |
| KJV | Jer 48:36 | split | got ten | both halves are words |
| KJV | Jer 49:2 | split | he ard | both halves are words |
| KJV | Ezek 3:7 | split | a nd | a one-letter word, and the joined word is not attested beside its neighbours |
| KJV | Ezek 13:7 | split | where as | both halves are words |
| KJV | Ezek 41:17 | split | a bout | a one-letter word beside a word printed elsewhere |
| KJV | Dan 2:34 | split | with out | both halves are words |
| KJV | Dan 8:18 | split | tow ard | both halves are words |
| KJV | Mic 5:6 | split | As syria | both halves are words |
| KJV | Zech 8:13 | split | heat hen, | both halves are words |
| KJV | Matt 4:12 | split | in to | both halves are words |
| KJV | Mark 4:24 | split | he ar: | both halves are words |
| KJV | John 9:25 | split | Whet her | both halves are words |
| KJV | John 12:49 | split | Fat her | both halves are words |
| KJV | Rom 6:22 | split | be come | both halves are words |
| KJV | 1 Cor 12:23 | split | honour able, | both halves are words |
| KJV | Phil 1:20 | split | ear nest | both halves are words |
| KJV | 1 Tim 2:10 | split | be cometh | both halves are words |
| KJV | Heb 1:6 | glued | firstbegotten | printed as a compound or the translation's own spelling, not two words |
| KJV | Heb 9:5 | glued | mercyseat | printed as a compound or the translation's own spelling, not two words |
| KJV | Jas 3:17 | split | intreat ed, | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| KJV | Rev 11:6 | split | he aven, | both halves are words |
| SLT | Gen 6:18 | split | in to | both halves are words |
| SLT | Gen 6:19 | split | in to | both halves are words |
| SLT | Gen 12:5 | split | Cana an; | both halves are words |
| SLT | Gen 13:10 | split | wi ll | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| SLT | Gen 19:8 | split | any thing; | both halves are words |
| SLT | Gen 19:19 | hyphen | over -taking | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| SLT | Gen 27:16 | glued | shegoats | printed as a compound or the translation's own spelling, not two words |
| SLT | Gen 37:17 | hyphen | They -removed | the joined form is printed nowhere else |
| SLT | Gen 45:19 | split | fat her | both halves are words |
| SLT | Gen 46:8 | split | first born | both halves are words |
| SLT | Gen 49:11 | hyphen | she -ass; | the joined form is printed nowhere else |
| SLT | Exod 12:34 | hyphen | kneading- bowls | the joined form is printed nowhere else |
| SLT | Exod 21:4 | split | for th | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| SLT | Exod 21:33 | split | the re, | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| SLT | Exod 34:5 | split | up on | both halves are words |
| SLT | Exod 40:35 | split | in to | both halves are words |
| SLT | Lev 10:9 | split | in to | both halves are words |
| SLT | Lev 14:46 | split | in to | both halves are words |
| SLT | Lev 15:4 | split | flow ing | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| SLT | Lev 16:3 | split | in to | both halves are words |
| SLT | Lev 16:23 | split | in to | both halves are words |
| SLT | Lev 16:26 | split | in to | both halves are words |
| SLT | Lev 16:28 | split | in to | both halves are words |
| SLT | Lev 17:12 | split | sojourn ing | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| SLT | Lev 18:19 | split | impuri ty | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| SLT | Lev 21:18 | hyphen | flat -nosed, | the joined form is printed nowhere else |
| SLT | Num 7:69 | split | ye ar, | both halves are words |
| SLT | Num 7:79 | hyphen | thirty- and | the joined form is printed nowhere else |
| SLT | Num 7:89 | split | in to | both halves are words |
| SLT | Num 14:29 | split | be ing | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| SLT | Num 14:30 | split | in to | both halves are words |
| SLT | Num 16:26 | split | any thing | both halves are words |
| SLT | Num 17:3 | split | up on | both halves are words |
| SLT | Num 20:10 | split | He ar, | both halves are words |
| SLT | Num 26:59 | split | Am ram, | both halves are words |
| SLT | Deut 3:14 | hyphen | Bashan- Havath-Jair, | the joined form is printed nowhere else |
| SLT | Deut 6:10 | split | in to | both halves are words |
| SLT | Deut 8:17 | glued | handmade | no sibling prints the two words |
| SLT | Deut 9:28 | split | in to | both halves are words |
| SLT | Deut 16:13 | split | wine press. | both halves are words |
| SLT | Deut 22:19 | split | fat her | both halves are words |
| SLT | Deut 23:1 | split | in to | both halves are words |
| SLT | Deut 23:2 | split | in to | both halves are words |
| SLT | Deut 23:3 | split | in to | both halves are words |
| SLT | Deut 23:8 | split | in to | both halves are words |
| SLT | Josh 6:22 | split | in to | both halves are words |
| SLT | Josh 9:23 | split | draw ing | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| SLT | Josh 10:19 | split | in to | both halves are words |
| SLT | Josh 13:19 | hyphen | Zarath -Shahar | the joined form is printed nowhere else |
| SLT | Josh 19:5 | hyphen | Hazor -Susah, | the joined form is printed nowhere else |
| SLT | Josh 19:6 | hyphen | Beth -Lehaoth, | the joined form is printed nowhere else |
| SLT | Josh 19:8 | hyphen | Baalath- Beor, | the joined form is printed nowhere else |
| SLT | Josh 19:26 | hyphen | Shihor -Libnah; | the joined form is printed nowhere else |
| SLT | Judg 2:1 | split | in to | both halves are words |
| SLT | Judg 4:22 | split | in to | both halves are words |
| SLT | Judg 6:24 | hyphen | Jehovah -peace: | the joined form is printed nowhere else |
| SLT | Judg 9:13 | hyphen | wine -making, | the joined form is printed nowhere else |
| SLT | Judg 9:27 | split | in to | both halves are words |
| SLT | Judg 9:46 | split | in to | both halves are words |
| SLT | Judg 9:53 | hyphen | mill -stone | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| SLT | Judg 13:4 | split | any thing | both halves are words |
| SLT | Judg 13:7 | split | any thing | both halves are words |
| SLT | Judg 18:18 | split | in to | both halves are words |
| SLT | Judg 20:40 | split | be hold, | both halves are words |
| SLT | 1 Sam 6:17 | split | A shdod | a one-letter word, and the joined word is not attested beside its neighbours |
| SLT | 1 Sam 12:4 | split | any thing | both halves are words |
| SLT | 2 Sam 5:8 | split | in to | both halves are words |
| SLT | 2 Sam 7:19 | split | rem oteness. | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| SLT | 2 Sam 12:31 | hyphen | threshing- sledge | the joined form is printed nowhere else |
| SLT | 2 Sam 19:9 | split | deliver ed | both halves are words |
| SLT | 2 Sam 24:22 | hyphen | threshing- rollers, | the joined form is printed nowhere else |
| SLT | 1 Kgs 7:47 | split | a n | a one-letter word, and the joined word is not attested beside its neighbours |
| SLT | 1 Kgs 11:27 | split | for tress | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| SLT | 1 Kgs 16:34 | split | first born | both halves are words |
| SLT | 2 Kgs 19:23 | split | in to | both halves are words |
| SLT | 2 Kgs 25:23 | split | appoint ed | both halves are words |
| SLT | 1 Chr 2:25 | split | first born, | both halves are words |
| SLT | 1 Chr 8:5 | split | Hur am. | both halves are words |
| SLT | 1 Chr 14:14 | split | a bout | a one-letter word beside a word printed elsewhere |
| SLT | 1 Chr 16:5 | split | A saph | a one-letter word beside a word printed elsewhere |
| SLT | 2 Chr 7:2 | split | in to | both halves are words |
| SLT | 2 Chr 20:2 | split | A ram | both halves are words |
| SLT | 2 Chr 23:16 | glued | cutout | no sibling prints the two words |
| SLT | 2 Chr 26:16 | split | in to | both halves are words |
| SLT | 2 Chr 29:32 | hyphen | bunt -offering | the joined form is printed nowhere else |
| SLT | 2 Chr 30:9 | split | a re | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| SLT | Neh 5:15 | split | la st | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| SLT | Neh 12:42 | split | Jeho nathan | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| SLT | Esth 5:10 | split | in to | both halves are words |
| SLT | Job 4:2 | split | with hold | both halves are words |
| SLT | Job 12:24 | split | a way. | both halves are words |
| SLT | Ps 95:11 | split | in to | both halves are words |
| SLT | Isa 4:5 | glued | afire | printed as a compound or the translation's own spelling, not two words |
| SLT | Isa 13:2 | split | in to | both halves are words |
| SLT | Isa 14:30 | split | first born | both halves are words |
| SLT | Isa 21:7 | split | horse men, | both halves are words |
| SLT | Isa 37:1 | split | in to | both halves are words |
| SLT | Isa 37:30 | hyphen | self -sown; | the joined form is printed nowhere else |
| SLT | Isa 40:31 | split | up on | both halves are words |
| SLT | Isa 63:2 | split | wine press? | both halves are words |
| SLT | Jer 16:5 | split | in to | both halves are words |
| SLT | Jer 16:8 | split | in to | both halves are words |
| SLT | Jer 27:5 | split | for th, | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| SLT | Jer 48:8 | split | up on | both halves are words |
| SLT | Jer 51:15 | split | habit able | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| SLT | Lam 1:10 | split | in to | both halves are words |
| SLT | Lam 1:10 | split | in to | both halves are words |
| SLT | Lam 4:12 | split | in to | both halves are words |
| SLT | Ezek 13:15 | split | plaster ing | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| SLT | Ezek 18:21 | split | just ice; | both halves are words |
| SLT | Ezek 40:19 | split | with out, | both halves are words |
| SLT | Ezek 41:2 | split | then ce: | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| SLT | Ezek 42:16 | hyphen | five -hundred | the joined form is printed nowhere else |
| SLT | Ezek 44:9 | split | in to | both halves are words |
| SLT | Ezek 44:21 | split | in to | both halves are words |
| SLT | Dan 5:10 | split | in to | both halves are words |
| SLT | Dan 12:1 | split | strai ts | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| SLT | Hos 9:4 | split | in to | both halves are words |
| SLT | Joel 3:13 | split | wine press | both halves are words |
| SLT | Amos 4:11 | hyphen | fire -brand | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| SLT | Obad 1:13 | split | in to | both halves are words |
| SLT | Mic 4:2 | split | mount ain | both halves are words |
| SLT | Mic 5:6 | split | in to | both halves are words |
| SLT | Hab 1:16 | hyphen | fish -net; | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| SLT | Zech 3:2 | hyphen | fire -brand | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| SLT | Matt 1:25 | split | first born | both halves are words |
| SLT | Matt 22:12 | split | muzzl ed. | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| SLT | Matt 27:5 | split | him self. | both halves are words |
| SLT | Mark 6:8 | hyphen | traveling- sack, | the joined form is printed nowhere else |
| SLT | Mark 11:25 | split | any thing | both halves are words |
| SLT | Mark 13:20 | split | shorten ed | both halves are words |
| SLT | Mark 15:39 | hyphen | Son- of | the joined form is printed nowhere else |
| SLT | Luke 6:25 | split | laugh ing | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| SLT | Luke 6:30 | hyphen | re -demand | the joined form is printed nowhere else |
| SLT | Luke 9:14 | split | thou sand | both halves are words |
| SLT | Luke 10:35 | hyphen | inn -keeper, | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| SLT | John 1:32 | split | up on | both halves are words |
| SLT | Acts 1:20 | hyphen | country -house | the joined form is printed nowhere else |
| SLT | Acts 2:46 | split | per severing | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| SLT | Acts 12:7 | split | dwell ing: | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| SLT | Acts 25:26 | split | some thing | both halves are words |
| SLT | Rom 2:4 | split | long suffering | both halves are words |
| SLT | Rom 8:29 | split | first born | both halves are words |
| SLT | 2 Cor 3:6 | split | a s | a one-letter word, and the joined word is not attested beside its neighbours |
| SLT | 2 Cor 6:6 | split | long suffering, | both halves are words |
| SLT | 2 Cor 8:23 | hyphen | co- worker | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| SLT | 2 Cor 9:10 | hyphen | sowing- season, | the joined form is printed nowhere else |
| SLT | 2 Cor 11:23 | hyphen | light -headed) | the joined form is printed nowhere else |
| SLT | Phil 1:20 | split | a shamed, | both halves are words |
| SLT | 2 Tim 3:10 | split | long suffering, | both halves are words |
| SLT | Heb 9:25 | split | in to | both halves are words |
| SLT | Heb 11:28 | split | first born | both halves are words |
| SLT | Rev 1:5 | split | first born | both halves are words |
| WBT | Gen 6:14 | hyphen | gopher -wood: | the joined form is printed nowhere else |
| WBT | Gen 14:10 | hyphen | slime -pits; | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| WBT | Gen 16:14 | hyphen | Beer -la-hai-roi; | the joined form is printed nowhere else |
| WBT | Gen 21:29 | split | them selves? | both halves are words |
| WBT | Gen 30:37 | hyphen | chesnut -tree; | the joined form is printed nowhere else |
| WBT | Gen 31:37 | hyphen | household -stuff? | the joined form is printed nowhere else |
| WBT | Gen 40:17 | hyphen | bake -meats | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| WBT | Gen 44:9 | split | whom soever | both halves are words |
| WBT | Exod 1:7 | split | be came | both halves are words |
| WBT | Exod 1:11 | hyphen | treasure -cities, | the joined form is printed nowhere else |
| WBT | Exod 7:11 | hyphen | wise -men, | the joined form is printed nowhere else |
| WBT | Exod 21:27 | hyphen | man- servant’s | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| WBT | Exod 24:10 | hyphen | sapphire -stone, | the joined form is printed nowhere else |
| WBT | Exod 29:40 | hyphen | tenth -portion | the joined form is printed nowhere else |
| WBT | Exod 38:8 | hyphen | looking -glasses | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| WBT | Lev 3:9 | hyphen | back- bone; | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| WBT | Lev 11:43 | split | your selves | both halves are words |
| WBT | Lev 14:13 | hyphen | holy- place: | the joined form is printed nowhere else |
| WBT | Num 20:13 | split | be cause | both halves are words |
| WBT | Num 24:6 | hyphen | lign -aloes | the joined form is printed nowhere else |
| WBT | Num 32:8 | hyphen | h- barnea | the joined form is printed nowhere else |
| WBT | Num 35:18 | hyphen | hand- weapon | the joined form is printed nowhere else |
| WBT | Deut 3:14 | hyphen | Bashan-havoth- jair, | the joined form is printed nowhere else |
| WBT | Deut 10:10 | hyphen | first -time, | the joined form is printed nowhere else |
| WBT | Deut 18:4 | hyphen | first- fruit | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| WBT | Josh 9:1 | split | he ard | both halves are words |
| WBT | Josh 15:6 | hyphen | Beth -hogla, | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| WBT | Josh 18:15 | hyphen | Kirjah -jearim, | the joined form is printed nowhere else |
| WBT | Josh 19:26 | split | a nd | a one-letter word, and the joined word is not attested beside its neighbours |
| WBT | Judg 19:11 | split | in to | both halves are words |
| WBT | 1 Sam 6:7 | hyphen | milch- cows | the joined form is printed nowhere else |
| WBT | 1 Sam 14:14 | hyphen | half- acre | the joined form is printed nowhere else |
| WBT | 1 Sam 21:15 | hyphen | mad -men, | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| WBT | 1 Kgs 20:18 | split | whet her | both halves are words |
| WBT | 2 Kgs 3:25 | hyphen | Kirhara- seth | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| WBT | 2 Kgs 4:35 | split | him self | both halves are words |
| WBT | 2 Kgs 4:42 | hyphen | Baal -shalisha, | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| WBT | 2 Kgs 6:9 | split | ha ve | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| WBT | 1 Chr 19:6 | hyphen | Syria -maachah, | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| WBT | 2 Chr 9:18 | hyphen | sitting -place, | the joined form is printed nowhere else |
| WBT | 2 Chr 18:25 | split | Am on | both halves are words |
| WBT | 2 Chr 18:33 | hyphen | chariot -man, | the joined form is printed nowhere else |
| WBT | Ezra 7:21 | split | he aven, | both halves are words |
| WBT | Neh 2:13 | hyphen | dragon- well, | the joined form is printed nowhere else |
| WBT | Neh 2:13 | hyphen | dung -port, | the joined form is printed nowhere else |
| WBT | Neh 9:15 | split | he aven | both halves are words |
| WBT | Esth 3:8 | split | a broad | both halves are words |
| WBT | Ps 42:7 | hyphen | water -spouts: | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| WBT | Ps 60:1 | hyphen | Shushan- eduth, | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| WBT | Ps 84:10 | hyphen | door -keeper | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| WBT | Prov 30:15 | hyphen | horse- leech | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| WBT | Song 7:4 | hyphen | fish -pools | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| WBT | Isa 38:8 | hyphen | sun- dial | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| WBT | Isa 47:13 | hyphen | star -gazers, | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| WBT | Isa 65:25 | split | serpen ts’ | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| WBT | Jer 31:21 | hyphen | way -marks, | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| WBT | Ezek 17:3 | hyphen | long- winged, | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| WBT | Ezek 27:5 | hyphen | ship- boards | the joined form is printed nowhere else |
| WBT | Dan 2:37 | split | he aven | both halves are words |
| WBT | Dan 5:16 | split | he ard | both halves are words |
| WBT | Obad 1:14 | hyphen | cross -way, | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| WBT | Hag 2:16 | hyphen | press- vat | the joined form is printed nowhere else |
| WBT | Zech 9:10 | hyphen | battle -bow | the joined form is printed nowhere else |
| WBT | Zech 10:4 | hyphen | battle -bow, | the joined form is printed nowhere else |
| WBT | Mark 2:23 | hyphen | corn- fields | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| WBT | Mark 10:46 | hyphen | highway- side | the joined form is printed nowhere else |
| WBT | Luke 6:1 | hyphen | corn- fields; | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| WBT | Luke 6:17 | hyphen | sea -coast | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| WBT | John 6:7 | hyphen | penny- worth | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| WBT | Acts 1:23 | split | a nd | a one-letter word, and the joined word is not attested beside its neighbours |
| WBT | Acts 5:19 | hyphen | prison- doors, | the joined form is printed nowhere else |
| WBT | Acts 18:3 | hyphen | tent -makers) | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| WBT | Acts 19:35 | hyphen | town- clerk | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| WBT | Acts 24:5 | hyphen | ring -leader | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| WBT | Rom 15:28 | split | sea led | both halves are words |
| WBT | 1 Cor 3:10 | hyphen | master -builder, | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| WBT | 2 Cor 9:5 | split | before hand | both halves are words |
| WBT | 1 Thess 3:2 | hyphen | fellow -laborer | the joined form is printed nowhere else |
| WBT | 1 Thess 5:14 | hyphen | feeble- minded, | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| WBT | Phlm 1:1 | hyphen | fellow- laborer, | the joined form is printed nowhere else |
| WBT | 1 Pet 2:1 | hyphen | evil -speakings, | the joined form is printed nowhere else |
| WBT | 1 Pet 2:19 | hyphen | thank -worthy, | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| WBT | 1 Pet 3:20 | hyphen | g- suffering | the joined form is printed nowhere else |
| WBT | 1 Pet 4:15 | hyphen | busy- body | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| WBT | Rev 1:18 | split | be hold, | both halves are words |
| WBT | Rev 17:4 | hyphen | scarlet -color, | the joined form is printed nowhere else |
| WBT | Rev 21:11 | hyphen | jasper -stone, | the joined form is printed nowhere else |
| WEB | Gen 18:11 | glued | childbe | no sibling prints the two words |
| WEB | Gen 36:22 | split | Hem an. | both halves are words |
| WEB | Gen 45:11 | split | house hold, | both halves are words |
| WEB | Exod 16:32 | hyphen | omer- full | the joined form is printed nowhere else |
| WEB | Exod 16:33 | hyphen | omer -full | the joined form is printed nowhere else |
| WEB | Exod 33:11 | split | a gain | both halves are words |
| WEB | Lev 21:8 | split | pr ofanes | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| WEB | Num 2:15 | hyphen | fifty- one | the joined form is printed nowhere else |
| WEB | Num 3:31 | split | lamp stand, | both halves are words |
| WEB | Num 4:14 | split | a bout | a one-letter word beside a word printed elsewhere |
| WEB | Deut 16:18 | split | Yahw eh | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| WEB | Deut 28:35 | split | can not | both halves are words |
| WEB | Deut 28:39 | split | har vest; | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| WEB | Josh 6:13 | split | sound ed | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| WEB | Josh 8:17 | split | Beth El | both halves are words |
| WEB | Josh 19:10 | split | the ir | both halves are words |
| WEB | 1 Sam 25:29 | split | Yahw eh | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| WEB | 1 Sam 31:4 | split | arm or | both halves are words |
| WEB | 2 Sam 8:13 | split | a re | a one-letter word, and the joined word is not attested beside its neighbours |
| WEB | 1 Kgs 2:42 | split | a broad | both halves are words |
| WEB | 1 Kgs 10:19 | split | be side | both halves are words |
| WEB | 1 Kgs 13:1 | split | Beth El: | both halves are words |
| WEB | 2 Kgs 4:10 | split | lamp stand. | both halves are words |
| WEB | 1 Chr 11:8 | split | a round, | both halves are words |
| WEB | 1 Chr 19:6 | split | Ha nun | both halves are words |
| WEB | 2 Chr 13:5 | split | Yahw eh, | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| WEB | 2 Chr 35:14 | split | be cause | both halves are words |
| WEB | Neh 1:11 | split | cup bearer | both halves are words |
| WEB | Neh 4:1 | split | he ard | both halves are words |
| WEB | Neh 5:14 | split | govern or | both halves are words |
| WEB | Esth 6:3 | split | be en | both halves are words |
| WEB | Job 24:11 | split | wine presses, | both halves are words |
| WEB | Ps 37:6 | split | noon day | both halves are words |
| WEB | Ps 55:15 | split | the ir | both halves are words |
| WEB | Prov 17:14 | split | a dam, | a one-letter word beside a word printed elsewhere |
| WEB | Isa 32:13 | split | up on | both halves are words |
| WEB | Isa 38:2 | split | Yahw eh, | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| WEB | Isa 46:7 | split | can not | both halves are words |
| WEB | Jer 16:11 | split | Yahw eh, | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| WEB | Jer 23:39 | split | a way | both halves are words |
| WEB | Jer 48:33 | split | wine presses: | both halves are words |
| WEB | Ezek 31:3 | hyphen | forest -like | the joined form is printed nowhere else |
| WEB | Dan 8:2 | split | El am; | both halves are words |
| WEB | Hos 7:2 | split | the ir | both halves are words |
| WEB | Joel 2:10 | split | earth quakes | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| WEB | Amos 4:8 | split | sw arming | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| WEB | Mic 1:2 | split | Yahw eh | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| WEB | Zech 8:22 | split | Yahw eh.” | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| WEB | Matt 18:26 | split | kneel ed | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| WEB | Matt 27:13 | split | he ar | both halves are words |
| WEB | Mark 14:4 | split | them selves, | both halves are words |
| WEB | Luke 7:12 | split | be hold, | both halves are words |
| WEB | Luke 21:36 | split | watchfu l | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| WEB | John 3:23 | split | be cause | both halves are words |
| WEB | Acts 6:12 | split | in to | both halves are words |
| WEB | Acts 27:39 | split | noti ced | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| WEB | 2 Cor 4:2 | split | our selves | both halves are words |
| WEB | 2 Cor 12:19 | split | our selves | both halves are words |
| WEB | Gal 2:18 | hyphen | law -breaker. | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| WEB | 1 Tim 2:14 | split | fall en | both halves are words |
| WEB | 2 Tim 3:6 | split | a way | both halves are words |
| WEB | 1 Pet 4:15 | split | evil doer, | both halves are words |
| YLT | Gen 12:5 | split | in to | both halves are words |
| YLT | Gen 19:38 | hyphen | Beni -Ammon | the joined form is printed nowhere else |
| YLT | Gen 23:6 | hyphen | burying- places | the joined form is printed nowhere else |
| YLT | Gen 24:41 | split | Jehov ah, | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| YLT | Gen 31:10 | split | up on | both halves are words |
| YLT | Gen 31:12 | split | up on | both halves are words |
| YLT | Gen 41:31 | split | repea ting | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| YLT | Gen 45:25 | split | in to | both halves are words |
| YLT | Gen 48:3 | split | Cana an, | both halves are words |
| YLT | Exod 2:6 | split | se eth | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| YLT | Exod 23:8 | hyphen | open -eyed, | the joined form is printed nowhere else |
| YLT | Exod 23:29 | split | ha th | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| YLT | Exod 23:30 | split | Ri ver: | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| YLT | Exod 34:20 | hyphen | ploughing -time | the joined form is printed nowhere else |
| YLT | Exod 38:8 | hyphen | looking- glasses | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| YLT | Lev 2:12 | hyphen | first -fruits—ye | the joined form is printed nowhere else |
| YLT | Lev 5:15 | split | prie st, | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| YLT | Lev 12:4 | split | ha th | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| YLT | Lev 13:55 | split | a spect, | a one-letter word, and the joined word is not attested beside its neighbours |
| YLT | Lev 13:55 | hyphen | front- part. | the joined form is printed nowhere else |
| YLT | Lev 14:20 | split | al so | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| YLT | Lev 19:34 | hyphen | mete -yard, | the joined form is printed nowhere else |
| YLT | Lev 20:12 | hyphen | daughter -in-law—both | the joined form is printed nowhere else |
| YLT | Lev 23:20 | hyphen | first -fruits— | the joined form is printed nowhere else |
| YLT | Lev 26:5 | hyphen | sowing -time; | the joined form is printed nowhere else |
| YLT | Num 1:20 | hyphen | first -born—their | the joined form is printed nowhere else |
| YLT | Num 6:14 | hyphen | she -lamb, | the joined form is printed nowhere else |
| YLT | Num 13:21 | split | in to | both halves are words |
| YLT | Num 21:23 | split | in to | both halves are words |
| YLT | Num 30:8 | hyphen | cast -out | the joined form is printed nowhere else |
| YLT | Deut 3:13 | hyphen | Bashan- Havoth-Jair, | the joined form is printed nowhere else |
| YLT | Deut 12:27 | hyphen | burnt -offerings—the | the joined form is printed nowhere else |
| YLT | Deut 25:2 | hyphen | wrong- doing, | the joined form is printed nowhere else |
| YLT | Deut 32:21 | hyphen | ‘no -god,’ | the joined form is printed nowhere else |
| YLT | Deut 32:25 | hyphen | inner -chambers—fear, | the joined form is printed nowhere else |
| YLT | Josh 2:6 | split | up on | both halves are words |
| YLT | Josh 4:3 | hyphen | standing -place | the joined form is printed nowhere else |
| YLT | Josh 7:6 | split | up on | both halves are words |
| YLT | Josh 15:11 | split | be en | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| YLT | Josh 19:33 | split | a nd | a one-letter word, and the joined word is not attested beside its neighbours |
| YLT | Josh 22:23 | split | up on | both halves are words |
| YLT | Judg 1:12 | hyphen | Kirjath- Sepher—and | the joined form is printed nowhere else |
| YLT | Judg 9:51 | split | up on | both halves are words |
| YLT | Judg 9:54 | split | die th. | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| YLT | Judg 11:16 | split | in to | both halves are words |
| YLT | Judg 13:5 | split | up on | both halves are words |
| YLT | Judg 16:17 | split | up on | both halves are words |
| YLT | Judg 16:25 | split | gl ad, | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| YLT | Judg 19:21 | split | in to | both halves are words |
| YLT | Judg 20:44 | split | a re | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| YLT | 1 Sam 2:28 | split | up on | both halves are words |
| YLT | 1 Sam 2:36 | split | in to | both halves are words |
| YLT | 1 Sam 4:13 | split | in to | both halves are words |
| YLT | 1 Sam 6:9 | hyphen | Beth- Shemesh—He | the joined form is printed nowhere else |
| YLT | 1 Sam 9:12 | split | in to | both halves are words |
| YLT | 1 Sam 9:13 | split | in to | both halves are words |
| YLT | 1 Sam 9:13 | split | in to | both halves are words |
| YLT | 1 Sam 9:14 | split | in to | both halves are words |
| YLT | 1 Sam 9:14 | split | in to | both halves are words |
| YLT | 1 Sam 9:22 | split | in to | both halves are words |
| YLT | 1 Sam 15:29 | hyphen | Pre -eminence | the joined form is printed nowhere else |
| YLT | 1 Sam 19:11 | hyphen | to -night— | the joined form is printed nowhere else |
| YLT | 1 Sam 20:42 | split | in to | both halves are words |
| YLT | 1 Sam 23:7 | split | in to | both halves are words |
| YLT | 1 Sam 26:3 | split | in to | both halves are words |
| YLT | 2 Sam 4:7 | split | in to | both halves are words |
| YLT | 2 Sam 6:16 | split | in to | both halves are words |
| YLT | 2 Sam 6:18 | split | ca using | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| YLT | 2 Sam 10:2 | split | in to | both halves are words |
| YLT | 2 Sam 10:14 | split | in to | both halves are words |
| YLT | 2 Sam 10:14 | split | in to | both halves are words |
| YLT | 2 Sam 12:20 | split | in to | both halves are words |
| YLT | 2 Sam 15:37 | split | in to | both halves are words |
| YLT | 2 Sam 15:37 | split | in to | both halves are words |
| YLT | 2 Sam 16:8 | split | in to | both halves are words |
| YLT | 2 Sam 16:15 | split | in to | both halves are words |
| YLT | 2 Sam 17:17 | split | in to | both halves are words |
| YLT | 2 Sam 17:22 | split | ha th | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| YLT | 2 Sam 19:3 | split | in to | both halves are words |
| YLT | 2 Sam 20:3 | hyphen | women- concubines— | the joined form is printed nowhere else |
| YLT | 2 Sam 24:6 | split | in to | both halves are words |
| YLT | 2 Sam 24:6 | split | in to | both halves are words |
| YLT | 2 Sam 24:7 | split | in to | both halves are words |
| YLT | 1 Kgs 1:41 | split | ha ve | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| YLT | 1 Kgs 1:51 | hyphen | to- day—he | the joined form is printed nowhere else |
| YLT | 1 Kgs 4:16 | hyphen | Ben -Hushai | the joined form is printed nowhere else |
| YLT | 1 Kgs 5:15 | split | ki ng | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| YLT | 1 Kgs 7:45 | split | a re | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| YLT | 1 Kgs 8:6 | split | ho use, | both halves are words |
| YLT | 1 Kgs 9:21 | split | up on | both halves are words |
| YLT | 1 Kgs 10:7 | split | decla red | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| YLT | 1 Kgs 11:17 | split | in to | both halves are words |
| YLT | 1 Kgs 11:18 | split | in to | both halves are words |
| YLT | 1 Kgs 12:7 | split | a rt | a one-letter word, and the joined word is not attested beside its neighbours |
| YLT | 1 Kgs 12:33 | split | up on | both halves are words |
| YLT | 1 Kgs 15:8 | split | do th | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| YLT | 1 Kgs 18:27 | split | a loud | both halves are words |
| YLT | 1 Kgs 18:36 | hyphen | evening -present, | the joined form is printed nowhere else |
| YLT | 1 Kgs 20:43 | split | in to | both halves are words |
| YLT | 1 Kgs 22:25 | split | in to | both halves are words |
| YLT | 2 Kgs 3:19 | split | ha ve | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| YLT | 2 Kgs 3:20 | hyphen | morning -present, | the joined form is printed nowhere else |
| YLT | 2 Kgs 4:32 | split | in to | both halves are words |
| YLT | 2 Kgs 6:20 | split | in to | both halves are words |
| YLT | 2 Kgs 6:23 | split | in to | both halves are words |
| YLT | 2 Kgs 7:4 | split | in to | both halves are words |
| YLT | 2 Kgs 7:14 | hyphen | chariot -horses, | the joined form is printed nowhere else |
| YLT | 2 Kgs 9:2 | split | in to | both halves are words |
| YLT | 2 Kgs 9:6 | split | in to | both halves are words |
| YLT | 2 Kgs 9:30 | split | in to | both halves are words |
| YLT | 2 Kgs 9:33 | split | trea deth | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| YLT | 2 Kgs 10:17 | split | in to | both halves are words |
| YLT | 2 Kgs 10:21 | split | in to | both halves are words |
| YLT | 2 Kgs 11:18 | split | in to | both halves are words |
| YLT | 2 Kgs 12:9 | split | in to | both halves are words |
| YLT | 2 Kgs 12:9 | split | in to | both halves are words |
| YLT | 2 Kgs 12:16 | split | in to | both halves are words |
| YLT | 2 Kgs 13:20 | split | in to | both halves are words |
| YLT | 2 Kgs 14:20 | split | up on | both halves are words |
| YLT | 2 Kgs 15:14 | split | in to | both halves are words |
| YLT | 2 Kgs 16:6 | split | in to | both halves are words |
| YLT | 2 Kgs 18:34 | split | Hen a, | both halves are words |
| YLT | 2 Kgs 23:34 | split | in to | both halves are words |
| YLT | 1 Chr 4:19 | hyphen | Abi -Keilah | the joined form is printed nowhere else |
| YLT | 1 Chr 5:26 | split | in to | both halves are words |
| YLT | 1 Chr 19:15 | split | in to | both halves are words |
| YLT | 1 Chr 19:15 | split | in to | both halves are words |
| YLT | 1 Chr 21:27 | split | turn eth | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| YLT | 1 Chr 24:19 | split | in to | both halves are words |
| YLT | 1 Chr 28:7 | split | he arts | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| YLT | 2 Chr 3:14 | split | up on | both halves are words |
| YLT | 2 Chr 6:20 | split | up on | both halves are words |
| YLT | 2 Chr 12:11 | split | go ing | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| YLT | 2 Chr 18:11 | hyphen | Ramath- Gilead | the joined form is printed nowhere else |
| YLT | 2 Chr 20:28 | split | in to | both halves are words |
| YLT | 2 Chr 25:28 | split | up on | both halves are words |
| YLT | 2 Chr 28:5 | split | in to | both halves are words |
| YLT | 2 Chr 28:9 | split | in to | both halves are words |
| YLT | 2 Chr 28:27 | split | in to | both halves are words |
| YLT | 2 Chr 29:16 | split | in to | both halves are words |
| YLT | 2 Chr 31:16 | split | in to | both halves are words |
| YLT | 2 Chr 32:1 | split | in to | both halves are words |
| YLT | 2 Chr 32:5 | split | out side | both halves are words |
| YLT | 2 Chr 34:9 | split | in to | both halves are words |
| YLT | 2 Chr 34:14 | split | in to | both halves are words |
| YLT | Ezra 5:2 | split | ha ve | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| YLT | Neh 4:11 | split | in to | both halves are words |
| YLT | Neh 6:10 | split | in to | both halves are words |
| YLT | Neh 6:10 | split | in to | both halves are words |
| YLT | Neh 9:25 | hyphen | digged- wells, | the joined form is printed nowhere else |
| YLT | Neh 10:29 | split | in to | both halves are words |
| YLT | Neh 10:29 | split | in to | both halves are words |
| YLT | Neh 10:34 | split | in to | both halves are words |
| YLT | Neh 13:15 | split | in to | both halves are words |
| YLT | Esth 8:15 | split | be en | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| YLT | Job 1:5 | hyphen | burnt -offerings—the | the joined form is printed nowhere else |
| YLT | Job 10:22 | hyphen | Death- shade—and | the joined form is printed nowhere else |
| YLT | Job 38:16 | split | in to | both halves are words |
| YLT | Job 39:29 | split | a far | both halves are words |
| YLT | Ps 40:2 | split | up on | both halves are words |
| YLT | Ps 42:7 | hyphen | water -spouts, | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| YLT | Ps 46:6 | split | for th | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| YLT | Ps 63:9 | split | in to | both halves are words |
| YLT | Ps 73:17 | split | in to | both halves are words |
| YLT | Ps 78:53 | split | confident ly, | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| YLT | Ps 96:8 | split | in to | both halves are words |
| YLT | Ps 105:23 | split | in to | both halves are words |
| YLT | Ps 108:10 | split | in to | both halves are words |
| YLT | Song 5:1 | split | in to | both halves are words |
| YLT | Isa 6:10 | split | ha th | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| YLT | Isa 21:11 | split | ca lling | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| YLT | Isa 28:13 | split | be en, | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| YLT | Isa 30:29 | split | in to | both halves are words |
| YLT | Isa 30:33 | split | brim stone, | both halves are words |
| YLT | Isa 37:29 | hyphen | self- sown | the joined form is printed nowhere else |
| YLT | Isa 41:19 | hyphen | fir -pine | the joined form is printed nowhere else |
| YLT | Isa 46:7 | split | up on | both halves are words |
| YLT | Jer 2:7 | split | in to | both halves are words |
| YLT | Jer 3:16 | split | up on | both halves are words |
| YLT | Jer 4:5 | split | in to | both halves are words |
| YLT | Jer 8:14 | split | in to | both halves are words |
| YLT | Jer 26:21 | split | in to | both halves are words |
| YLT | Jer 34:10 | split | in to | both halves are words |
| YLT | Jer 44:8 | split | in to | both halves are words |
| YLT | Jer 49:34 | split | ha th | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| YLT | Jer 49:36 | split | in to | both halves are words |
| YLT | Jer 50:6 | hyphen | crouching- place. | the joined form is printed nowhere else |
| YLT | Lam 2:10 | split | up on | both halves are words |
| YLT | Lam 5:18 | split | up on | both halves are words |
| YLT | Ezek 3:15 | hyphen | Tel -Ahib, | the joined form is printed nowhere else |
| YLT | Ezek 8:3 | split | in to | both halves are words |
| YLT | Ezek 11:23 | split | mount ain, | both halves are words |
| YLT | Ezek 11:24 | split | in to | both halves are words |
| YLT | Ezek 12:13 | split | in to | both halves are words |
| YLT | Ezek 14:22 | split | com ing | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| YLT | Ezek 16:8 | split | in to | both halves are words |
| YLT | Ezek 17:4 | split | in to | both halves are words |
| YLT | Ezek 17:20 | split | in to | both halves are words |
| YLT | Ezek 18:20 | split | do th | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| YLT | Ezek 22:1 | split | a bominations, | a one-letter word, and the joined word is not attested beside its neighbours |
| YLT | Ezek 27:5 | hyphen | double -boarded | the joined form is printed nowhere else |
| YLT | Ezek 27:11 | split | up on | both halves are words |
| YLT | Ezek 27:30 | split | up on | both halves are words |
| YLT | Ezek 34:16 | split | a way | both halves are words |
| YLT | Ezek 43:11 | split | ho use, | both halves are words |
| YLT | Ezek 43:18 | split | up on | both halves are words |
| YLT | Ezek 44:17 | split | up on | both halves are words |
| YLT | Ezek 47:3 | split | east ward, | both halves are words |
| YLT | Ezek 47:12 | split | up on | both halves are words |
| YLT | Dan 1:2 | split | in to | both halves are words |
| YLT | Dan 1:2 | split | in to | both halves are words |
| YLT | Dan 3:24 | split | ha th | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| YLT | Dan 12:10 | split | wise ly | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| YLT | Hos 1:5 | split | ha th | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| YLT | Hos 4:15 | split | in to | both halves are words |
| YLT | Joel 3:5 | split | in to | both halves are words |
| YLT | Amos 5:19 | split | in to | both halves are words |
| YLT | Amos 8:10 | split | up on | both halves are words |
| YLT | Hab 2:11 | glued | holdfast | no sibling prints the two words |
| YLT | Zeph 1:3 | hyphen | stumbling- blocks—the | the joined form is printed nowhere else |
| YLT | Zeph 2:15 | hyphen | crouching- place | the joined form is printed nowhere else |
| YLT | Zech 10:4 | hyphen | battle -bow, | the joined form is printed nowhere else |
| YLT | Zech 14:7 | hyphen | evening -time—there | the joined form is printed nowhere else |
| YLT | Mal 2:3 | split | a way | both halves are words |
| YLT | Mal 4:6 | split | ha th | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| YLT | Matt 5:22 | split | ha th | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| YLT | Matt 16:17 | hyphen | Bar -Jona, | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| YLT | Matt 16:17 | split | gat es | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| YLT | Matt 17:25 | hyphen | poll -tax? | the joined form is printed nowhere else |
| YLT | Matt 24:17 | hyphen | house -top—let | the joined form is printed nowhere else |
| YLT | Mark 2:23 | hyphen | corn- fields—and | the joined form is printed nowhere else |
| YLT | Luke 2:8 | hyphen | night -watches | the joined form is printed nowhere else |
| YLT | Luke 10:34 | split | up on | both halves are words |
| YLT | Luke 19:4 | split | up on | both halves are words |
| YLT | Luke 21:21 | split | in to | both halves are words |
| YLT | John 4:28 | hyphen | water- jug, | the joined form is printed nowhere else |
| YLT | John 6:17 | split | in to | both halves are words |
| YLT | Acts 14:15 | hyphen | like -affected | the joined form is printed nowhere else |
| YLT | Acts 14:21 | split | d iscipled | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| YLT | Acts 16:14 | split | Thyatir a, | a one-letter word, and the joined word is not attested beside its neighbours |
| YLT | Acts 18:3 | hyphen | tent -makers | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| YLT | Acts 24:6 | split | wi sh | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| YLT | Acts 27:41 | hyphen | hinder -part | the joined form is printed nowhere else |
| YLT | Rom 5:6 | split | ail ing, | thin evidence: the word stands alone fewer than three times and no sibling prints it |
| YLT | Rom 8:29 | hyphen | fore -appoint, | the joined form is printed nowhere else |
| YLT | Rom 8:30 | hyphen | fore- appoint, | the joined form is printed nowhere else |
| YLT | Rom 14:13 | hyphen | stumbling- stone | the joined form is printed nowhere else |
| YLT | Rom 16:7 | hyphen | fellow -captives, | the joined form is printed nowhere else |
| YLT | 1 Cor 3:10 | hyphen | master -builder, | line-break hyphen: the word is printed solid, so the hyphen would have to go too |
| YLT | 1 Cor 15:15 | split | be cause | both halves are words |
| YLT | 2 Cor 7:6 | hyphen | cast -down—God—He | the joined form is printed nowhere else |
| YLT | 2 Cor 9:8 | split | every thing | both halves are words |
| YLT | Gal 3:24 | hyphen | child- conductor—to | the joined form is printed nowhere else |
| YLT | Gal 5:26 | hyphen | vain- glorious—one | the joined form is printed nowhere else |
| YLT | 1 Thess 4:9 | hyphen | God- taught | the joined form is printed nowhere else |
| YLT | 1 Thess 4:16 | hyphen | chief- messenger, | the joined form is printed nowhere else |
| YLT | Titus 1:10 | hyphen | mind -deceivers—especially | the joined form is printed nowhere else |
| YLT | Titus 1:10 | hyphen | vain -talkers, | the joined form is printed nowhere else |
| YLT | Phlm 1:15 | hyphen | age -duringly | the joined form is printed nowhere else |
| YLT | Heb 12:9 | glued | ising | no sibling prints the two words |
| YLT | Heb 12:28 | hyphen | well- pleasingly, | the joined form is printed nowhere else |
| YLT | Jas 5:4 | hyphen | in -gathered | the joined form is printed nowhere else |
| YLT | 2 Pet 1:9 | hyphen | dim- sighted, | the joined form is printed nowhere else |
| YLT | 2 John 1:5 | split | an other, | both halves are words |
| YLT | Rev 1:9 | hyphen | fellow -partner | the joined form is printed nowhere else |
| YLT | Rev 11:8 | hyphen | broad -place | the joined form is printed nowhere else |
| YLT | Rev 17:4 | hyphen | scarlet -colour, | the joined form is printed nowhere else |
| YLT | Rev 21:21 | hyphen | broad- place | the joined form is printed nowhere else |
