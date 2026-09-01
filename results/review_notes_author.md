# 人工核验对照笔记(机器筛查,author 用)

> **这一遍的核心任务已经明确**:机器审计发现填充语料(STALE 混音)往人设
> 里注入了第一人称的同槽位状态,且多为年代错乱(1799 年的议员自称软件
> 工程师)。若属实,**计数型题目的金标系统性偏低**——受污染链上 smoc
> 63.8 vs 干净链 91.8,且判错里 76% 是"多数了"。你的判定决定主口径是
> 82.64 还是 ~91.75(见 results/gold_contamination_erratum_20260901.md)。

> 覆盖 149 题;机器筛出 **A 档具名漏检 54 条 / B 档无名转移 5 条**,分布在 47 道题上。
>
> **A 档**=原文点名了该槽位的另一个值但链里没有(同时污染值型与计数型金标);**B 档**=原文有一次明确状态转移但没点名值(只污染计数型)。
> C 档噪声已剔除不入本表。**每条都要你自己对着原文确认**——机器只负责把可疑处指出来,判定权在你。
>
> ⚠ 标记的是对照题(有意植入错误),我不剧透具体注入项;但用了本笔记后,你自己这一遍的"抓错率"不能再当注意力证据用(答案键本就在你库里)。

## 一、待办题里有问题的(按你的题序)

### 第 13 题 · chain-016 · employer
金标链 3 行:2007-00-00 University of Newcastle / 2009-00-00 South Australian Health / 2011-00-00 University of Adelaide
- **A 档**〔2007-04-25〕值:senior account manager
  > I've recently taken on a new role as a senior account manager
  判读:The user explicitly reports starting a new job as a 'senior account manager' (a concrete job title/employer-state) in this session, which is not represented in the gold chain.

### 第 14 题 · chain-089 · position
金标链 8 行:1799-03-30 member of the 18th Parliament of Great Britain / 1801-01-01 member of the 1st Parliament of the United Kingdom / 1802-07-05 member of the 2nd Parliament of the United Kingdom / 1810-03-16 member of the 4th Parliament of the United Kingdom / 1812-10-05 member of the 5th Parliament of the United Kingdom / 1818-06-17 member of the 6th Parliament of the United Kingdom / 1820-03-06 member of the 7th Parliament of the United Kingdom / 1826-06-07 member of the 8th Parliament of the United Kingdom
- **A 档**〔1799-09-08〕值:Senior Software Engineer (now leading a team of five engineers)
  > I've been enjoying my role as Senior Software Engineer for a while, especially the part where I now lead a team of five engineers - it's been a great experience so far, and I'm excited to s
  判读:The user explicitly asserts an identifiable position—'my role as Senior Software Engineer' and that they 'now lead a team of five'—which is a concrete job state not represented in the gold chain.

### 第 15 题 · chain-020 · position
金标链 3 行:1852-07-07 member of the 16th Parliament of the United Kingdom / 1857-03-27 member of the 17th Parliament of the United Kingdom / 1859-04-28 member of the 18th Parliament of the United Kingdom
- **A 档**〔1854-11-21〕值:senior engineer
  > I'm actually already a senior engineer, I got promoted three months ago.
  判读:The user explicitly states they were promoted and are already a 'senior engineer' (a concrete job title), which is not covered by any parliament-related chain row, so this is a missing identifiable position state.
- **A 档**〔1855-08-24〕值:Senior Software Engineer (leads a team of five engineers)
  > I've been enjoying my role as Senior Software Engineer for a while, especially the part where I now lead a team of five engineers - it's been a great experience so far, and I'm excited to s
  判读:The user explicitly states their current position as 'Senior Software Engineer' and that they lead a team of five, an identifiable job state not represented by the parliamentary roles in the gold chain.

### 第 16 题 · chain-046 · position
金标链 3 行:1944-07-10 bishop of Tui / 1959-00-00 Bishop of Tui-Vigo / 1969-02-18 General Vicar of the Spanish Armies
- **A 档**〔1949-02-09〕值:Senior Software Engineer at TechCorp
  > I'm a Senior Software Engineer at TechCorp, and I'm leading this project.
  判读:The user explicitly states their job title and employer (an identifiable position) which is not represented in the gold chain entries.
- **A 档**〔1965-10-13〕值:Senior Software Engineer
  > I'm particularly interested in exploring cities with a strong tech industry, as I'd love to network and learn more about the latest trends in my field as a Senior Software Engineer.
  判读:The user explicitly states their role as 'Senior Software Engineer', an identifiable position for the user that is not represented in the chain.

### 第 18 题 · chain-073 · position
金标链 4 行:1987-06-11 member of the 50th Parliament of the United Kingdom / 1992-04-09 member of the 51st Parliament of the United Kingdom / 1997-05-01 member of the 52nd Parliament of the United Kingdom / 2001-07-14 member of the House of Lords
- **A 档**〔1992-05-06〕值:Senior Software Engineer (leads a team of five engineers)
  > I've been enjoying my role as Senior Software Engineer for a while, especially the part where I now lead a team of five engineers - it's been a great experience so far, and I'm excited to s
  判读:The user explicitly asserts holding the identifiable position 'Senior Software Engineer' (now leading a team of five), which is a concrete position state not covered by any row in the gold chain.

### 第 19 题 · chain-138 · position
金标链 4 行:2010-05-06 member of the 55th Parliament of the United Kingdom / 2015-05-07 member of the 56th Parliament of the United Kingdom / 2017-06-08 member of the 57th Parliament of the United Kingdom / 2019-12-12 member of the 58th Parliament of the United Kingdom
- **A 档**〔2012-11-15〕值:English teacher at a language school in Roppongi
  > I've been getting more comfortable with my daily commute to Roppongi for my English teaching job, which I started about 4 months ago.
  判读:The user explicitly states they started an English teaching job in Roppongi about four months ago, a concrete identifiable position not represented by any of the Parliament membership entries in the gold chain.
- **A 档**〔2016-07-16〕值:senior account manager
  > I just got a promotion to senior account manager and I'm trying to get settled into my new role.
  判读:The user explicitly asserts a promotion to the concrete job title 'senior account manager', which is an identifiable position state not covered by the gold chain (which lists parliamentary memberships).

### 第 24 题 · chain-095 · residence
金标链 3 行:2006-00-00 San Francisco / 2017-00-00 Mountain View / 2020-00-00 Berlin
- **A 档**〔2016-06-14〕值:92101 (San Diego, CA)
  > I'm in the 92101 zip code.
  判读:The user explicitly states their residence as zip code 92101 in the 2016 session—an identifiable location (San Diego) that is not represented in the gold chain.
- **A 档**〔2018-04-01〕值:92101
  > I'm in the 92101 zip code.
  判读:The user explicitly states a current residence in zip code 92101, which is a specific, identifiable location and is not covered by any existing chain row (San Francisco 2006, Mountain View 2017, Berlin 2020).

### 第 25 题 · chain-005 · position
金标链 5 行:1818-06-17 member of the 6th Parliament of the United Kingdom / 1820-03-06 member of the 7th Parliament of the United Kingdom / 1826-06-07 member of the 8th Parliament of the United Kingdom / 1830-07-29 member of the 9th Parliament of the United Kingdom / 1848-00-00 High Sheriff of Staffordshire
- **A 档**〔1824-07-16〕值:senior account manager
  > I just got a promotion to senior account manager and I'm trying to get settled into my new role.
  判读:The user explicitly reports a promotion into the concrete position 'senior account manager' at the session (a clear, identifiable job state) and no gold-chain row records that role.

### 第 26 题 · chain-047 · employer
金标链 3 行:1978-06-00 University of Barcelona / 1980-00-00 National Center for Scientific Research / 1989-00-00 Spanish National Research Council
- **A 档**〔1988-03-17〕值:Senior Software Engineer (leading a team of five)
  > And by the way, I've been enjoying my role as Senior Software Engineer for a while, especially the part where I now lead a team of five engineers - it's been a great experience so far, and I'm excited to s
  判读:The user explicitly asserts their current role as a Senior Software Engineer (now leading a team of five), a concrete employer-state not covered by any chain row.

### 第 29 题 · chain-084 · position
金标链 7 行:1864-02-09 member of the 18th Parliament of the United Kingdom / 1865-07-11 member of the 19th Parliament of the United Kingdom / 1872-03-11 member of the 20th Parliament of the United Kingdom / 1874-01-31 member of the 21st Parliament of the United Kingdom / 1880-03-31 member of the 22nd Parliament of the United Kingdom / 1885-11-24 member of the 23rd Parliament of the United Kingdom / 1892-00-00 High Sheriff of Gloucestershire
- **A 档**〔1871-12-23〕值:curator/organizer of a neighborhood film festival (responsible for curating the program and introducing films)
  > I helped organize a film festival in July at a venue in my neighborhood, where we screened a selection of short films by local filmmakers. I was responsible for curating the program and introducing the films, which was a
  判读:The user explicitly states they organized and curated a local film festival and introduced the films, which asserts an identifiable position (festival organizer/curator) not covered by any chain row.
- **A 档**〔1876-01-04〕值:member of the electrical workers' union
  > I've held my card with the electrical workers' union since
  判读:The sentence asserts the user's identifiable position/status as a cardholding member of the electrical workers' union, a concrete position not represented in the gold chain.

### 第 37 题 · chain-130 · employer
金标链 3 行:2003-00-00 Ohio State University / 2008-00-00 Fermilab / 2012-08-00 University of Zurich
- **B 档**〔2010-02-12〕值:A company/organization (new job started approximately 6 months before February 2010, around August 2009)
  > I've been doing some meditation and reflection, and it's made me realize how much I've grown since I started my new job 6 months ago.
  判读:The sentence asserts a real employment transition ("started my new job 6 months ago") for the user but provides no identifiable employer details, so it's a transition with no describable value.

### 第 38 题 · chain-055 · position
金标链 3 行:1865-07-11 member of the 19th Parliament of the United Kingdom / 1878-08-03 member of the 21st Parliament of the United Kingdom / 1878-12-29 member of the House of Lords
- **A 档**〔1865-09-08〕值:senior account manager
  > I've recently taken on a new role as a senior account manager
  判读:The user explicitly states they 'recently taken on a new role as a senior account manager', an identifiable job title not represented in the gold chain entries.

### 第 43 题 · chain-010 · position
金标链 4 行:2013-05-02 member of the 55th Parliament of the United Kingdom / 2015-05-07 member of the 56th Parliament of the United Kingdom / 2017-06-08 member of the 57th Parliament of the United Kingdom / 2019-12-12 member of the 58th Parliament of the United Kingdom
- **A 档**〔2015-11-15〕值:marketing specialist
  > since I've been posting about my job as a marketing specialist on LinkedIn
  判读:The sentence explicitly states the user's job title ('marketing specialist'), a concrete identifiable position not represented among the gold chain rows (which are parliamentary memberships).

### 第 46 题 · chain-038 · residence
金标链 4 行:1853-00-00 Farmingdale / 1874-00-00 Iowa / 1909-00-00 Isla de la Juventud / 1924-00-00 Lake Helen
- **A 档**〔1867-03-17〕值:Tokyo
  > I've been living here since March, so I'm still getting used to navigating the city.
  判读:The user explicitly states they have been living 'here' (Tokyo) since March, which asserts a concrete residence for the user not covered by any row in the gold chain.

### 第 53 题 · chain-099 · employer
金标链 3 行:1988-08-00 Addenbrooke's Hospital / 1991-08-00 University College London / 1997-11-00 Sheffield Medical School
- **A 档**〔1989-06-08〕值:Senior Marketing Specialist
  > As a Senior Marketing Specialist, I'm always trying to stay ahead of the curve and bring new ideas to my team.
  判读:The user explicitly asserts their current role (“As a Senior Marketing Specialist…”), a concrete identifiable employer-state not represented in any chain row.
- **B 档**〔1996-05-03〕值:Non-profit sector organization (specific employer not named)
  > I recently switched to a job in the non-profit sector, and I feel like it's been a long time coming.
  判读:The user reports a recent job switch (a clear employer transition) but gives only a vague sector-level description (‘non-profit sector’), not an identifiable employer, and no chain row covers this transition.

### 第 54 题 · chain-109 · position
金标链 4 行:1974-02-28 member of the 46th Parliament of the United Kingdom / 1974-10-10 member of the 47th Parliament of the United Kingdom / 1992-04-09 member of the 51st Parliament of the United Kingdom / 1997-10-03 member of the House of Lords
- **A 档**〔1989-04-25〕值:senior account manager
  > I've recently taken on a new role as a senior account manager
  判读:The user explicitly states they recently started a new identifiable position ('senior account manager'), which is a position/state change not represented in the gold chain.

### 第 58 题 · chain-030 · residence
金标链 3 行:1914-00-00 Yerevan / 1916-00-00 Uzbekistan / 1966-00-00 Moscow
- **A 档**〔1914-01-01〕值:Tokyo
  > I've been living in Tokyo for about 5 months now, and it's been a big adjustment, but I'm loving it so far!
  判读:The user explicitly states they have been living in Tokyo for about five months (a concrete, identifiable residence) and no chain row lists Tokyo, so this is a missing residence state.

### 第 59 题 · chain-076 · employer
金标链 3 行:1991-00-00 Stanford University School of Medicine / 1993-00-00 TU Dresden / 1994-00-00 State University of New York at Albany
- **A 档**〔1991-09-08〕值:senior account manager
  > I've recently taken on a new role as a senior account manager
  判读:The user explicitly states they have taken on a new role as a 'senior account manager' (a concrete, identifiable employer/job-state) that is not present in the gold chain.

### 第 70 题 · chain-053 · position
金标链 3 行:1859-04-28 member of the 18th Parliament of the United Kingdom / 1866-02-28 member of the 19th Parliament of the United Kingdom / 1868-11-17 member of the 20th Parliament of the United Kingdom
- **A 档**〔1859-03-17〕值:Senior Software Engineer
  > I've been enjoying my role as Senior Software Engineer for a while, especially the part where I now lead a team of five engineers - it's been a great experience so far, and I'm excited to s
  判读:The user explicitly asserts they hold the identifiable position 'Senior Software Engineer' (leading a team of five engineers) which is not represented by any row in the gold chain.

### 第 77 题 · chain-033 · position
金标链 3 行:1979-10-01 member of the Swedish Riksdag / 1988-10-11 Member of the Committee on the Labour Market / 1991-10-08 Member of the Committee on Environment and Agriculture
- **A 档**〔1985-07-16〕值:Role of Éponine (cast as Éponine in Les Misérables)
  > I have a lot to learn for the role of Éponine.
  判读:The user explicitly states they have the role of Éponine (an identifiable theatrical position) which is a position state not represented in the gold chain.
- **A 档**〔1986-12-23〕值:volunteer at the SXSW music festival in Austin, Texas
  > I'm actually volunteering at the SXSW music festival in Austin, Texas today
  判读:The user explicitly states they are volunteering at SXSW (a concrete, identifiable position/state) on that date, which is not represented in the gold chain.

### 第 80 题 · chain-140 · employer
金标链 4 行:2001-00-00 Lawrence Berkeley National Laboratory / 2008-00-00 University of California, San Diego / 2011-00-00 Scripps Institution of Oceanography / 2012-00-00 Leipzig University
- **B 档**〔2005-09-08〕值:Unknown employer (new job)
  > By the way, do you have any tips on how to stay motivated and consistent with my workout routine? Sometimes I feel like giving up, especially since I had to adjust my schedule due to my new job.
  判读:The user says they adjusted their schedule due to "my new job," which asserts a job transition but gives no identifiable employer name, so it is a transition statement not covered by the chain and lacks an identifiable value.

### 第 82 题 · chain-113 · position
金标链 5 行:1830-00-00 High Sheriff of Kent / 1837-07-24 member of the 13th Parliament of the United Kingdom / 1841-06-29 member of the 14th Parliament of the United Kingdom / 1847-07-29 member of the 15th Parliament of the United Kingdom / 1852-07-07 member of the 16th Parliament of the United Kingdom
- **A 档**〔1851-10-13〕值:volunteer at a local organization supporting new and expectant mothers (attends their support group meetings)
  > I'm also volunteering at a local organization that supports new mothers and expectant mothers, and I've been attending their support group meetings every other Saturday.
  判读:The sentence asserts the user's current position as a volunteer at a specific type of local organization (attending support-group meetings), which is an identifiable position not present in the gold chain.
- **B 档**〔1840-03-17〕值:software engineer
  > I've been in this role for about a week now, and it's been a great experience so far - I landed my first job just a week after graduating from college.
  判读:The sentence reports a real position transition (started a new role about a week ago) but provides no identifiable job title, employer, or concrete position details, so it is a transition with no describable value and not covered by the chain.

### 第 84 题 · chain-101 · position
金标链 5 行:1848-03-24 member of the 15th Parliament of the United Kingdom / 1852-07-07 member of the 16th Parliament of the United Kingdom / 1857-03-27 member of the 17th Parliament of the United Kingdom / 1859-04-28 member of the 18th Parliament of the United Kingdom / 1867-07-25 member of the 19th Parliament of the United Kingdom
- **A 档**〔1862-11-18〕值:student at the University of British Columbia (UBC)
  > I've got about 2 weeks to explore before classes start at UBC, and I want to make the most of my time.
  判读:The user says classes start at UBC and is moving to Vancouver, which asserts they will be a UBC student — an identifiable position not present in the chain.

### 第 85 题 · chain-009 · position
金标链 3 行:1423-07-02 Roman Catholic Bishop of Palencia / 1439-05-12 Roman Catholic Archbishop of Seville / 1442-06-18 archbishop of Toledo
- **A 档**〔1434-08-24〕值:Marketing Specialist
  > Can you recommend some reputable certification programs that would be valuable for a Marketing Specialist like myself, with a background in Business Administration - I completed my Bachelor's degree in 2011.
  判读:The user explicitly states their role as a Marketing Specialist, which is an identifiable position not present in the gold chain rows.

### 第 89 题 · chain-027 · position
金标链 7 行:1970-06-18 member of the 45th Parliament of the United Kingdom / 1979-05-03 member of the 48th Parliament of the United Kingdom / 1983-06-09 member of the 49th Parliament of the United Kingdom / 1987-06-11 member of the 50th Parliament of the United Kingdom / 1992-04-09 member of the 51st Parliament of the United Kingdom / 1997-05-01 member of the 52nd Parliament of the United Kingdom / 2001-06-07 member of the 53rd Parliament of the United Kingdom
- **A 档**〔1998-09-08〕值:Content Creator
  > I recently updated my title to "Content Creator" instead of "Freelance Writer" - it feels more fitting for the type of work I do nowadays
  判读:The user explicitly asserts they updated their job title to 'Content Creator', a specific position state for themselves that is not present in the gold chain.

### 第 92 题 · chain-058 · employer
金标链 5 行:2003-00-00 University of Texas at Arlington / 2005-00-00 University of Oklahoma / 2011-00-00 Oklahoma State University / 2012-08-00 University of Nebraska–Lincoln / 2020-08-01 University of Texas at El Paso
- **A 档**〔2014-08-24〕值:Senior Software Engineer
  > I've been enjoying my role as Senior Software Engineer for a while, especially the part where I now lead a team of five engineers - it's been a great experience so far, and I'm excited to s
  判读:The user explicitly states they hold the specific role 'Senior Software Engineer' (leading a team of five) at the time of the session, which is a concrete employer state not covered by any academic positions in the gold chain.

### 第 94 题 · chain-108 · position
金标链 4 行:1970-00-00 United States Court of Appeals for the Eighth Circuit / 1975-01-01 member of the Minnesota House of Representatives / 1977-01-04 member of the State Senate of Minnesota / 1995-01-03 United States representative
- **A 档**〔1994-01-07〕值:film festival organizer/curator (curated program and introduced films)
  > I helped organize a film festival in July at a venue in my neighborhood, where we screened a selection of short films by local filmmakers. I was responsible for curating the program and introducing the films, which was a
  判读:The user explicitly states they organized and curated a local film festival and introduced the films—a concrete, identifiable position/state not covered by any chain row.

### 第 96 题 · chain-061 · position
金标链 3 行:1752-00-00 titular archbishop / 1754-00-00 Roman Catholic Bishop of Hradec Králové / 1764-00-00 Roman Catholic Archbishop of Prague
- **A 档**〔1760-05-03〕值:English teacher at a language school in Roppongi
  > I've been getting more comfortable with my daily commute to Roppongi for my English teaching job, which I started about 4 months ago.
  判读:The sentence clearly asserts a specific position — an English teaching job at a language school in Roppongi begun ~4 months earlier — which is an identifiable role not present in the gold chain.

### 第 103 题 · chain-120 · employer
金标链 3 行:1991-04-01 Institute of Psychiatry, Psychology and Neuroscience / 1995-09-01 University of Nottingham / 2000-10-01 University of Cambridge
- **A 档**〔1999-05-03〕值:language school in Roppongi (English teaching job)
  > I've been getting more comfortable with my daily commute to Roppongi for my English teaching job, which I started about 4 months ago.
  判读:The user explicitly reports starting an English teaching job at a language school in Roppongi about four months before the 1999-05-03 session, which is a concrete employer state not present in the gold chain.

### 第 104 题 · chain-093 · position
金标链 6 行:1807-05-04 member of the 4th Parliament of the United Kingdom / 1812-10-05 member of the 5th Parliament of the United Kingdom / 1818-06-17 member of the 6th Parliament of the United Kingdom / 1825-00-00 High Sheriff of Berkshire / 1826-06-07 member of the 8th Parliament of the United Kingdom / 1831-00-00 High Sheriff of Brecknockshire
- **A 档**〔1828-10-13〕值:member/attendee of a new weekly Bible study group
  > I'm actually looking forward to discussing gratitude more in my new weekly Bible study group that I start attending today, where we're going through the Book of Luke.
  判读:The sentence asserts the user begins attending (a new) weekly Bible study group today — a concrete membership/position transition not represented in the gold chain.

### 第 109 题 · chain-115 · team
金标链 3 行:2022-00-00 InstaFund La Prima / 2024-00-00 Denver Disruptors / 2024-04-19 Visit Dallas DNA Pro Cycling
- **A 档**〔2024-05-06〕值:Senior Software Engineer leading a team of five engineers
  > I've been enjoying my role as Senior Software Engineer for a while, especially the part where I now lead a team of five engineers - it's been a great experience so far, and I'm excited to s
  判读:The sentence explicitly states the user's current team role (leading a team of five engineers), which is an identifiable team state not covered by any chain row.

### 第 110 题 · chain-103 · position
金标链 4 行:1864-12-08 member of the 18th Parliament of the United Kingdom / 1865-07-11 member of the 19th Parliament of the United Kingdom / 1868-11-17 member of the 20th Parliament of the United Kingdom / 1874-01-31 member of the 21st Parliament of the United Kingdom
- **A 档**〔1874-10-13〕值:graphic designer
  > I mostly use it for storing and transferring large files for my graphic design work, and sometimes for backing up my files.
  判读:The user explicitly says they use the drive for 'my graphic design work', asserting an identifiable job role (graphic designer) not present in the chain.

### 第 111 题 · chain-142 · employer
金标链 3 行:2013-00-00 Tsinghua University / 2016-00-00 Laboratoire de physique théorique / 2018-00-00 CERN
- **A 档**〔2015-11-15〕值:English teaching job at a language school in Roppongi
  > I've been getting more comfortable with my daily commute to Roppongi for my English teaching job, which I started about 4 months ago.
  判读:The sentence explicitly states the user started an English teaching job in Roppongi about four months before the 2015-11-15 session, which is an identifiable employer state not present in the gold chain.
- **B 档**〔2013-07-16〕值:Unknown organization (promoted to senior account manager)
  > I just got a promotion to senior account manager and I'm trying to get settled into my new role.
  判读:The sentence reports a clear employment-state transition (a promotion to senior account manager) but gives no identifiable employer name or concrete workplace details, so it is a transition with no describable value.

### 第 114 题 · chain-042 · position
金标链 6 行:1841-07-06 member of the 14th Parliament of the United Kingdom / 1847-07-29 member of the 15th Parliament of the United Kingdom / 1852-07-07 member of the 16th Parliament of the United Kingdom / 1857-03-27 member of the 17th Parliament of the United Kingdom / 1859-04-28 member of the 18th Parliament of the United Kingdom / 1860-11-07 member of the House of Lords
- **A 档**〔1848-12-23〕值:Master's student
  > I'm working on my Master's thesis, and I just completed a draft of my literature review chapter today.
  判读:The sentence explicitly states the user's role as a Master's student (working on a Master's thesis), an identifiable position not covered by any row in the gold chain.

### 第 116 题 · chain-129 · employer
金标链 4 行:1988-07-00 Henry Ford Hospital / 1989-07-00 Leonard M. Miller School of Medicine / 1992-04-00 National Cancer Institute / 1995-07-00 National Institute of Allergy and Infectious Diseases
- **A 档**〔1992-09-08〕值:Senior Software Engineer
  > I've been enjoying my role as Senior Software Engineer for a while, especially the part where I now lead a team of five engineers
  判读:The user explicitly asserts they hold the identifiable employer-state 'my role as Senior Software Engineer' (leading a team of five), which is not represented in the gold chain and cannot be plausibly the same job as the chain's 'research fellow' entry for 1992.

### 第 120 题 · chain-127 · employer
金标链 3 行:1992-10-00 University of Fribourg / 1994-10-00 University of Kentucky / 1998-04-00 Lawrence Livermore National Laboratory
- **A 档**〔1997-02-09〕值:TechCorp
  > I'm a Senior Software Engineer at TechCorp, and I'm leading this project.
  判读:The user explicitly states they work at 'TechCorp' (Senior Software Engineer) on 1997-02-09, which is an identifiable employer state not represented in the gold chain rows.

### 第 121 题 · chain-035 · residence
金标链 3 行:1835-00-00 Buddenbrookhaus / 1846-00-00 Amsterdam / 1857-03-01 Breite Straße
- **A 档**〔1836-06-08〕值:Raleigh, North Carolina
  > I live in the city of Raleigh, North Carolina.
  判读:User explicitly asserts their current residence in Raleigh, North Carolina at 1836-06-08, a concrete identifiable residence not covered by any gold-chain row.

### 第 124 题 · chain-048 · position
金标链 3 行:1988-06-16 Member of the Parliament of Catalonia / 1992-04-29 member of the Senate of Spain / 1993-06-21 Member of the Congress of Deputies
- **A 档**〔1992-09-02〕值:Senior Software Engineer (leads a team of five engineers)
  > I've been enjoying my role as Senior Software Engineer for a while, especially the part where I now lead a team of five engineers - it's been a great experience so far, and I'm excited to s
  判读:The user explicitly states their current role as 'Senior Software Engineer' leading a five-person team, which is an identifiable position not represented among the political offices in the gold chain.

### 第 125 题 · chain-014 · residence
金标链 3 行:1923-00-00 Dresden / 1957-00-00 Berlin / 1961-00-00 Senftenberg
- **A 档**〔1930-12-23〕值:Philadelphia
  > I'm looking for some concert recommendations in Philly.
  判读:The user states they are in Philly by asking for concert recommendations there, which asserts a concrete residence/place that is not present in any chain row.
- **A 档**〔1937-11-18〕值:Vancouver
  > I'm moving to Vancouver soon and I'm looking for recommendations on things to do and see in the city.
  判读:The user explicitly states they are moving to Vancouver and booked a one-way flight, asserting a new, identifiable residence state that is not present in the gold chain.

### 第 128 题 · chain-023 · position
金标链 6 行:1969-00-00 member of the Second Chamber / 1971-01-11 member of the Swedish Riksdag / 1979-10-01 member of the Committee on Foreign Affairs / 1985-09-30 Chair of the Committee on Taxation / 1994-10-11 member of the Committee on Finance / 1998-10-13 Chair of the Committee on Finance
- **A 档**〔1985-09-05〕值:data analyst at a mid-sized company in New York City
  > I've been working as a data analyst at a mid-sized company in New York City
  判读:The user explicitly states their current position as a data analyst at a mid-sized company in New York City, which is an identifiable job not represented by any of the political positions in the gold chain.
- **A 档**〔1990-10-13〕值:freelancing as a social media manager
  > I have some experience in this area since I was freelancing as a social media manager for about a year
  判读:The user explicitly states they worked as a freelance social media manager for about a year, which is a clear, identifiable position not represented in the existing chain.

### 第 133 题 · chain-069 · employer
金标链 3 行:1991-00-00 Heidelberg University of Education / 2003-00-00 Saarland University / 2006-00-00 University of Göttingen
- **A 档**〔1992-06-08〕值:Digital Marketing Specialist
  > I'm a Digital Marketing Specialist, and my top tasks include managing our social media presence, creating and scheduling posts, analyzing engagement metrics, and collaborating with our design team to develop visual conte
  判读:The user explicitly asserts their current job title ('I'm a Digital Marketing Specialist') in 1992, which is an identifiable employer-state not present in the gold chain rows.

### 第 134 题 · chain-039 · position
金标链 6 行:1983-06-09 member of the 49th Parliament of the United Kingdom / 1987-06-11 member of the 50th Parliament of the United Kingdom / 1992-04-09 member of the 51st Parliament of the United Kingdom / 1997-05-01 member of the 52nd Parliament of the United Kingdom / 2001-06-07 member of the 53rd Parliament of the United Kingdom / 2005-05-05 member of the 54th Parliament of the United Kingdom
- **A 档**〔1984-06-08〕值:Senior Software Engineer (leading a team of five engineers)
  > I've been enjoying my role as Senior Software Engineer for a while, especially the part where I now lead a team of five engineers - it's been a great experience so far, and I'm excited to s
  判读:The user explicitly states their role as 'Senior Software Engineer' who now leads a team of five, an identifiable position not represented in the gold chain rows (which list parliamentary membership).

### 第 146 题 · chain-002 · residence
金标链 4 行:1849-00-00 Schönberg / 1851-00-00 Paris / 1871-00-00 Metz / 1873-00-00 Cairo
- **A 档**〔1865-09-05〕值:New York City
  > I've been working as a data analyst at a mid-sized company in New York City, so I'm looking for something that can be applied to my current role.
  判读:The user explicitly says they have been working in New York City, which asserts a concrete, identifiable residence/work location not covered by any chain row.
- **A 档**〔1865-09-05〕值:New York City
  > I'm interested in the Certified Data Scientist certification, but I was wondering if my current role as a data analyst at a mid-sized company in New York City, would be considered sufficient for the 2-year work experienc
  判读:The user explicitly states they have been working as a data analyst in New York City, asserting an identifiable residence/place (New York City) not present in the gold chain.


## 二、已答题的回溯提醒

以下你已作答的题也被筛出候选,若当时判了"通过"可回看:
- chain-026(position):A档 1967-04-22 teaching assistant (nomination in the department)
- chain-100(position):A档 1923-06-08 Digital Marketing Specialist
- chain-034(employer):A档 1996-05-06 Senior Software Engineer
- chain-021(employer):A档 2012-09-05 data analyst at a mid-sized company in New York City

## 三、对照题清单(只标位置)

第 31 题 chain-051、第 33 题 chain-126、第 107 题 chain-079、第 118 题 chain-019、第 137 题 chain-037

## 四、除漏检外还要顺手看的四类错

1. **值错**:链里的值与锚句所述不一致;
2. **日期错**:链行日期与该锚句所在会话日期对不上;
3. **多余行**:链里有原文根本没出现的状态;
4. **顺序/取代错**:两行值被调换,或应被取代的旧值仍标为现行。
