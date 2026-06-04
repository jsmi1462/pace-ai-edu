User Story:
There are many resources for improving teacher practice, but they are in non standard formats and distributed all over the internet. Furthermore, a challenge of private school teachers is the broad leeway and scope of their differences of practice and the non-standardized format of instruction. Given this, this project attempts to remedy this situation by doing the following. One, passing educational literature from across the Internet, converting it into a standardized format, and finding the most relevant articles based on discipline and grade level for each teacher. The teacher also will add a tailoring string so that each week or each month, as we progress on the project, the teacher will receive 3 to 5 articles that are carefully tailored to their exact grade level, discipline, and teaching practice style, as well as areas that they want to improve in, along with lesson ideas that they can execute the very next day. The goal is highly personalized, efficient synopsis of educational literature for private school teacher teachers at Pace Academy. The execution will be as follows. The script will be running on an M4 Mac mini at Pace Academy that is reachable through Tailscale. This will host a large language model that is intern hosted through LM Studio. It will also host a database that will contain the articles, the user data to accomplish account management, and will be authenticated through Cloudflare zero trust, so that only users with the Pace Academy domain are able to utilize the service. The database will also be hosted on the Mac mini. The goal is for a local, extremely low cost architecture._app.PY contains all the implementation for another medical literature script. That does the same thing. Use this as a Reference.
PRIORITIES:
LOCAL
RUNNING on the Mac Mini
Vercel hosting of the React front end
LLM and database hosted on the Mac Mini
Cloudflare 0 trust to do user authentication AND to handle accessability from outside the local network. 
Tech stack:
React and Node front end, hosted on Vercel.
Postgres Database for user management, article storage, vectorization as needed for greater parsing speed
LM Studio hosting LLM.
User page contains:
Time as a teacher
tailoring string
Password?
Email contains:
3-5 article citations
Summaries of the articles and WHY IT MATTERS TO YOU personally, this specific teacher
3-5 things to try.
QQuestions:
Weekly or monthly?