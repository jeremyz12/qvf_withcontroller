# v2.4 填充会话年代错乱标记汇总(批 34 扫描副产物,2026-09-03)

- 标记数 1014,涉及 138/144 链(链均 7.3,最多 25);角色 {'user': 952, 'assistant': 62}
- 按会话年代:{'1420s': 3, '1430s': 2, '1750s': 10, '1760s': 5, '1770s': 5, '1780s': 6, '1790s': 4, '1800s': 8, '1810s': 5, '1820s': 6, '1830s': 26, '1840s': 52, '1850s': 75, '1860s': 49, '1870s': 31, '1880s': 8, '1890s': 2, '1910s': 3, '1920s': 13, '1930s': 22, '1940s': 14, '1950s': 8, '1960s': 7, '1970s': 38, '1980s': 101, '1990s': 209, '2000s': 178, '2010s': 116, '2020s': 8}
- 性质:v2.0 起的填充语料(STALE 混音)本身写于现代,会话日期回填到人物生平年代,于是 1800–1990 年代的会话里出现互联网、智能手机、Instagram 等。**不改变任何金标**(与四个槽位无关),属语料真实感缺陷,入 datasheet 已知瑕疵条目(此前记录 583 例为规则匹配下限,本次 LLM 扫描 1,014 例)。
- 处置建议:不在 v2.5 删除(删掉会毁掉填充的话题多样性且不影响主张);若日后重建填充池,按会话年代过滤技术词。

## 示例(每链一条,前 25 链)

| 链 | 会话日期 | 引文 |
|---|---|---|
| wikiP108005-Q89851845 | 2001-12-23 | By the way, my tweet about the movie got 15 retweets, which is a big deal for me! |
| wikiP108012-Q61996585 | 1996-06-14 | I just finished reading "The Nightingale" by Kristin Hannah on February 10th |
| wikiP108007-Q59456157 | 2001-01-07 | I recently attended the New York Film Festival and got to see the world premiere of "The French Dispatch" |
| wikiP108009-Q64855331 | 2008-11-15 | I'm glad I got accepted into UC Berkeley for the fall semester 2023, it's a dream come true! |
| wikiP108006-Q67650882 | 2014-01-04 | continuous autofocus mode on my Canon EOS 80D, especially when paired with my new Sigma 150-600mm lens |
| wikiP108013-Q41591689 | 1991-01-01 | Can you help me figure out what kind of power adapters I'll need for my new laptop, Dell XPS 13, and my new sm |
| wikiP108004-Q54196276 | 2003-02-09 | What's the latest on Patrick Mahomes' stats and performance this season? |
| wikiP108003-Q63411963 | 2002-09-08 | I think I'll go with the Logitech MX Master 3. |
| wikiP108000-Q59200022 | 1985-01-01 | I think I'll start with Todoist and Evernote since I've heard a lot about them. |
| wikiP108008-Q53283502 | 2014-06-08 | I've been using my Fitbit Charge 3 to track my sleep patterns |
| wikiP108011-Q42430132 | 1971-06-08 | I've been listening to a lot of podcasts lately, including 10 episodes of a particular show where I took notes |
| wikiP108001-Q53458422 | 2003-03-17 | I just finished listening to the entire series of "How I Built This" podcast over the past month, all 20 episo |
| wikiP108002-Q57686589 | 2007-03-20 | specifically The Daily from The New York Times |
| wikiP108010-Q53284080 | 2009-03-17 | I attended a Phoebe Bridgers concert there with my coworker, Sarah, last month and it was amazing! |
| wikiP108015-Q53953422 | 1985-01-01 | I'm trying to create a content calendar for my social media platforms. Can you help me brainstorm some post id |
| wikiP108024-Q60644344 | 2004-04-01 | I just finished reading the script of "Hamilton" |
| wikiP108017-Q61756107 | 1983-03-17 | I've been using a fitness app to track my workouts and progress |
| wikiP108016-Q57079433 | 1978-01-01 | Send a personalized email or LinkedIn message within 24-48 hours |
| wikiP108014-Q56648183 | 2012-01-01 | especially after watching "Hamilton" on Disney+ a few weeks back |
| wikiP108021-Q37837264 | 1991-01-04 | I'm looking to focus on social media advertising, especially Facebook Ads |
| wikiP108019-Q41470166 | 1996-01-04 | I've also realized that I tend to spend more time on Facebook, especially in groups related to my favorite TV  |
| wikiP108025-Q56879021 | 1990-08-27 | interested in "Atomic Habits" and "Essentialism" |
| wikiP108022-Q53509286 | 2004-09-05 | I just finished binge-watching the entire season of 'Stranger Things' today and I'm still reeling from the fin |
| wikiP108020-Q42614637 | 1993-02-12 | recommend some TV shows similar to "Stranger Things"? I just started watching it on a Friday evening and got h |
| wikiP108027-Q20829689 | 2009-09-05 | I'm looking for some recommendations on games similar to The Last of Us Part II. By the way, I just finished i |
