00:00 Samyak Sahu: Yeah, so now we are starting recording. Um yeah, so so here's what I want, like uh and and I want you to like think about this from first principles.
00:13 Samyak Sahu: And the reason why I'm not introducing you to my project, and I'm Asking you to do this is because I want a fresh perspective on my approach.
00:21 Samyak Sahu: Okay. I've come up with an approach of my own. I'm not sure if it's working or not. You may come up with something that is better.
00:29 Samyak Sahu: So, which is why this is like the first task that I want to have. Get you up and running on.
00:36 Samyak Sahu: So there's this guy, a creator, who runs by the name of Bin Jiang and he makes videos in communication. Okay, he has posted.
00:48 Samyak Sahu: Video where he said the ultimate 30-day plan to master your communication skills, where he basically breaks down like there's a method or there's an approach of working on stuff that he shares.
01:05 Samyak Sahu: To improve your communication skills, I have linked the video here. I can send this to you separately as well. Actually, once the recording is stopped, you will get yourself a loom that will have all the links that we post here as comments.
01:21 Samyak Sahu: That mood itself.
01:22 siddhu s: It will be
01:23 Samyak Sahu: like easy for you to access once you get that. So, the video.
01:28 siddhu s: And yeah.
01:29 Samyak Sahu: So, the goal is very simple. The goal is that we have to productize the video. In a sense that we need to make an agent out of the video.
01:43 Samyak Sahu: That is it.
01:46 siddhu s: How or what is the purpose of the agent should be, or something? So the
01:51 Samyak Sahu: agent's purpose should be. Be that it stands as a proxy, or should I say, as an assistant to the creator and the agent.
02:10 Samyak Sahu: Stands as an assistant to the creator and allows the user to accomplish what the creator suggested.
02:18 siddhu s: In that video.
02:20 Samyak Sahu: Yes. Okay. So the goal is. That after 30 days, there should be some noticeable improvement in the way users communicate, like their public speaking or whatnot.
02:38 Samyak Sahu: And we want to build a System that allows us to keep the user on track during the course of this entire thing.
02:50 Samyak Sahu: What I've set up for you is a bot. It's called, if you look up on text, Telegram, it would be called Vinjian Bot or something else, I think.
03:08 Samyak Sahu: Yeah, so this is the bot name. Like, if you search this on Telegram, you'll actually. Find the bot itself. This bot will have a bot ID that I can share separately.
03:19 Samyak Sahu: And you basically need to basically get this system up and running in such a way that. If I tomorrow come to this bot and if I say hi to it, it understands me and it is able to help me out in realizing what is being written or what is the roadmap on this
03:42 siddhu s: video. So basically, you just share a link of the video. No,
03:45 Samyak Sahu: no,
03:46 siddhu s: no, no, no, no, no,
03:46 Samyak Sahu: not the link, not the link. I mean, that bad, but we like we can start by sharing the link of the video.
03:51 Samyak Sahu: But this is a 30-day plan, right? This is not a 10-minute video. The problem is that we are trying to solve is that this is a 10-minute video, but it only has a plan, there's no action around that plan.
04:01 Samyak Sahu: There's no proactiveness to that plan. You consume the video and you are done. But what about the key learnings from that video?
04:10 Samyak Sahu: Right? How do you get the user to come back to that reference again? How do you make the user to actually follow what is being mentioned here.
04:19 Samyak Sahu: This is a very Sarah's shift problem but but it's it's a very like it it's a different problem space, but the shape of the problem is very which is why you know I want us to like think about this a bit.
04:36 Samyak Sahu: We can like go up and spin up a new product in of itself, but this is more of a project that will probably help you understand how these systems work and how we can build a template or a playbook.
04:50 Samyak Sahu: Around these such a system where you have a video, there's a plan on it. How do you make an agent auto that now?
04:56 Samyak Sahu: How do you make that agent execute that plan on a longer term and keep track of the number of days that have passed, the progress of the user, and how do you measure all of that?
05:05 Samyak Sahu: And how do you? adjust that plan on the fly in case something goes wrong. Let's say if this video suggests that over the thirty days you need to give a check in every single day and the user misses out on two days in a row, how would that agent then react?
05:19 Samyak Sahu: How would that agent change that plan? Right.
05:23 siddhu s: Okay.
05:23 Samyak Sahu: Basically, that is what we're doing at Cellus as well. This
05:26 siddhu s: is spoken about this in the first interview. We discussed about this. Yeah. So,
05:32 Samyak Sahu: adaptive planning and proactive messages. That's basically what we need to build. In this, you'll also see that there will be a lot of skills that you may need to seed.
05:48 Samyak Sahu: There may be some connectors that you may need to see. For example, you may ask the at The connectors would not be that difficult to set up for this example, particularly.
05:58 Samyak Sahu: You will only need to set up your game. This would be telegram, and you can then come up with your own memory system.
06:10 Samyak Sahu: To be like a good fun exploration for you to understand what kind of memory systems work, whether you need to stick to the native memory layer, or do you want to use Obsidian, or do you want to use something like Moncho, or do you want to use something on Super Memory, whatever.
06:27 Samyak Sahu: Right, and yeah, just make sure that the context bloat is managed well so you can run like jobs at a regular interval that helps.
06:42 Samyak Sahu: Helps the user consolidate their thing basically helps the user not run into issues like loss of context, or it does not need to.
06:59 Samyak Sahu: Bad responses because the memory is too full. If there's something that, how do we auto-pressure? And the most important part is whatever harness you're using.
07:11 Samyak Sahu: I mean, I am using Hermes. So, I mean, if I were you, I would have. Started from Hermes, but if you want, I like you are free to use something like a plot managed agent, or you are free to use even something like Warsaw ACP, Google ACP, whatever works.
07:30 Samyak Sahu: Sorry, you're. Use any of this, whatever works for you. But the goal of this should be that it should not behave like an agent person in the sense that.
07:47 Samyak Sahu: it should not throw system errors. It should not or actually let it be it's okay. If we sh show system errors for now, that will be fine.
07:56 Samyak Sahu: But it it it should the concentration should look nat feel natural. It should not feel like you are using A computer talk.
08:05 Samyak Sahu: Like the computer should be able to build out a conversation with the person, and it should actually the tone, you can borrow the tone from Vinjiang itself.
08:19 Samyak Sahu: Like from the transcripts of his videos or from the posts that he has written. So it should sound like him.
08:26 Samyak Sahu: It should not be like, okay, you totally make it like make it like Win. Like you don't have to do that, but you can say that this is Win's.
08:35 Samyak Sahu: Or this is wins sidekick, or whatever you want to call it. And yeah, this is just have fun doing that.
08:42 Samyak Sahu: Okay.
08:43 siddhu s: So, yeah, this is like
08:44 Samyak Sahu: one activity. Open exploration, I'm eager to understand. What are the kind of approaches that you make here? What are the kind of judgment calls that you make?
08:53 Samyak Sahu: And with everything, you should have some understanding. Can
08:57 siddhu s: you just show me the screen again, you know, the X scale, but I'll just take a foot.
09:03 Samyak Sahu: And I think that's the way. Okay. Yeah, you get it. You get it in the zoom itself. So yeah, so the constraints are that you need to make it sound as less robotic as possible.
09:26 Samyak Sahu: If system errors do not come, then that would be great. But I would not want you to spend too much time on that at the start.
09:33 Samyak Sahu: I would want you to set up the system. First, set up the core architecture and have a sense of why we are doing what we are doing, right?
09:43 Samyak Sahu: Because that is what the long-term learning out of this project is. This project itself may not be of any use for us, but it will.
09:51 Samyak Sahu: At least help you understand what it is that we're doing, and what are the learnings that you've taken here that you can apply onto
09:59 siddhu s: this team? Yeah, right.
10:02 Samyak Sahu: So that is it. Do you have any questions in the meanwhile? Feel free to reach out if you have anything like we can like whatever works for you, we can get on like calls every other day or every day, whatever will be fine for you.
10:18 Samyak Sahu: One thing that I want as a deliverable would be like if you can record like a five-minute summary. Or a five-minute room of what you have been trapped to because we may not be able to like catch each other on the call.
10:29 Samyak Sahu: You see, the saw that, like, it was a really two days between us hiking for the first time. First time.
10:34 Samyak Sahu: So you can like record a five-minute loom, five to ten minutes, whatever works for you, and just go through what you have done and how is the agent coming about, where you are stuck, where you need help.
10:47 Samyak Sahu: And we may be able to sort that out in an Basic manner, or if you need, we can like get on the call the next day.
10:53 Samyak Sahu: I'll be reviewing those rooms every day by the end of it, expecting something to come up by whatever time you're comfortable.
11:01 Samyak Sahu: So I'll review it in the morning or probably so yeah.
11:07 siddhu s: Yeah, so you know, I was wondering, just give me today and tomorrow, I'll shoot back to PG nearby my office.
11:14 siddhu s: You know, I'll get my all setup set up, and from Saturday, I'll start working on it. Is that fine? Yeah, I mean,
11:21 Samyak Sahu: you can start. Some exploration. I don't know. Yeah,
11:24 siddhu s: I'll start exploration now. I'll go learn about it.
11:27 Samyak Sahu: Yeah, it's okay if you don't implement anything, but just do some research, understand what you would be needing, and how would you be coming about it.
11:38 Samyak Sahu: Solution to this. Like, look at open source repos, look at the kind of integrations that we're making, make trade-offs, start thinking about this at least.
11:48 Samyak Sahu: And yeah, record a Loom and share that with me. And I'd be happy if you use Excuse. Because that's a very visual way of describing anything, and the like the easier or like the yeah, the more comfortable you get with it, the better it will be for you in the long run.
12:06 Samyak Sahu: Like, even if you're explaining anything to anyone, it's a Very useful tool.
12:12 siddhu s: Yeah. Yeah. You
12:14 Samyak Sahu: can share that. That itself is fine. And you can like start working whenever you are ready with your setup.
12:20 siddhu s: Okay. Also, I was wondering, you know, k i c if you want, you could just uh get an API key and you could share it with me.
12:26 siddhu s: I'd Start using for the agents.
12:28 Samyak Sahu: API key for API key
12:31 siddhu s: for Hermes or for any of these agents for no harnesses.
12:38 Samyak Sahu: I mean, API key for hardnesses, what like there would be no API key for. If you want uh LLMs, then I can share that with you.
12:48 Samyak Sahu: Uh
12:48 siddhu s: no, yeah, I mean, that only, you know, okay, if basically we need to for this to work, it will e it will either work on an Open AI or an Anthropic side.
12:56 Samyak Sahu: Yeah, that will be the LS L for that. Can it provide you anything, like
13:01 siddhu s: uh yeah,
13:02 Samyak Sahu: like if you need open AI keys, if you need like let's say yeah, some some key new resource subscriptions or yeah, you can can create your own API keys out of the subscriptions that you get.
13:15 Samyak Sahu: Or, if you need any specific thing, I can be out with that.
13:18 siddhu s: Yeah, so I'll just, you know, go today, I'll go through Hermes once, I'll set it up, I'll go through Loom, I'll go through all the other things, and yeah, by tomorrow, I'll not.
13:31 siddhu s: End of tonight, helping you make requirements, or you know, but by tomorrow, I'll tomorrow Saturday I'll plan, say what is my approach, or something like that.
13:39 siddhu s: Yeah, yeah,
13:40 Samyak Sahu: yeah, yeah, okay, then, yeah, just go through it once if you have, like, I think we are already on the third and uh.
13:47 Samyak Sahu: Obviously, we're running a little short on time. We've gotten like a few new users on board that we need to onboard now.
13:55 Samyak Sahu: So the system is getting heavier. So I would like you to start working on the real thing as soon as possible.
14:00 Samyak Sahu: But before that, it will be good for you. As a long-term investment, to spend some time on this project.
14:07 siddhu s: So
14:08 Samyak Sahu: I would like, can you get the first room out by tonight? First room.
14:16 siddhu s: I
14:16 Samyak Sahu: mean, the first video of this instruction. Lo let's keep this as day one. Today is six and uh yeah, by the end of the day you can like submit whatever progress you have made uh as like a five minute update.
14:30 Samyak Sahu: It would be even smaller, it maybe two, three minutes, that does not matter, but there should be something. uh for me to look at.
14:36 Samyak Sahu: And we can then look at what should be the next uh course of action for us. I can make comments on that in line and you can like look into them and start working on the real thing tomorrow and the day after and the days to So, today's third, then we will be needing September 18th as the time when this
14:59 Samyak Sahu: gets completed. Can you make
15:02 siddhu s: it September 20th? Because you know, I just read a couple of days I might need shifting. Back to my office, nearby my office.
15:09 siddhu s: I'll take a PG nearby. Because right now, my office is in Electronic City and I'm staying at my friend's place, which is in Marthali.
15:16 siddhu s: So every day I travel like one and a half
15:19 Samyak Sahu: hours
15:21 siddhu s: back to my office. So I just thought, you know, I've been looking. For PGs yesterday and today, I'll finalize something and I'll get moved back to my PGL, move back to a PGL, set it up, and you know, I'll start working so that I don't spend three, four hours a day just traveling and wasting around my
15:35 siddhu s: time and that such.
15:38 Samyak Sahu: I mean, we can look into that. I was thinking that for the initial POC, you may not even need a week.
15:45 Samyak Sahu: But, like, whatever comes next would be refinements. So, the core functionality is built in like three, four days only. So, let's keep going, and then we'll see when.
15:56 Samyak Sahu: To stop and went to like cut over to the real production environment. And yeah, I think that could happen well before 20th, or it may take 20th as well.
16:09 Samyak Sahu: But I wrote. Think we should be waiting out on 20th now because that would be anyway too late. We'll actually be making a lot of sales between now and then.
16:21 Samyak Sahu: So, yeah, I would need some. But, but Child didn't come out in like five, six days only. Once you start doing it, then you'll realize that it's not that hard after all.
16:33 Samyak Sahu: Okay. Yeah. Okay.
16:38 siddhu s: So, yeah, I'll just set it up. I'll go through with it. Yeah, I'll just plan about it, you know, key what so.
16:44 siddhu s: Supposed to do, like, think about you know, what my idea how to get this up running, and yeah, by the by the end of today, or the Legislative even by tomorrow morning, I'll share you a couple of minutes loom.
16:56 siddhu s: Yeah, we'll just put your ideas and yeah.
17:01 Samyak Sahu: I'm like working my thing on my thing. I'll keep reviewing and add comments or any suggestions that I have. Okay.
17:10 Samyak Sahu: But yeah, let me know if you have any questions in the memo. Else. Yeah, I think that's it. If you want, so yeah, right now, actually, I'm in the process of incorporation.
17:26 Samyak Sahu: So, I mean, everything for everything to go official, I think, first of all, there will. Let's give it this one or two weeks, and then I'll be sort of the paperwork, and actually, you know, we can get you up and running on the real thing, and which is something that you can take away with you as well
17:43 Samyak Sahu: . As a standing record of, let's say, this is the term that you've worked, this is how we start. Start. Right now, it's like I'm just setting up that system.
17:51 Samyak Sahu: So, like, yeah. I can like send you
17:57 siddhu s: an email or something,
17:58 Samyak Sahu: that's whatever works to just make this official so that you can. Yeah, show it as as a proof of, I don't know, like how how you should make that be, but yeah.
18:15 Samyak Sahu: That's the thing to
18:16 siddhu s: think about later, right now.
18:17 Samyak Sahu: Yeah, I mean, that's later. That is something that I'm like, that is on my mind. But otherwise, you would be expected to build everything, the paperwork and everything to me, and the API keys, how to manage the plans, and etc.
18:31 Samyak Sahu: Other things. Even you won't have to worry too much about what tools would be using. But your job is simply to like explore the best solution to the problems and whatever you're working on, and yeah, to just get them all.
18:48 Samyak Sahu: Okay, yeah,
18:49 siddhu s: I will get to that. I know.
18:52 Samyak Sahu: Okay, bye. At the end of this, I think by the end of week one or week two, uh whenever you are like done, I think eighty percent once you're done with eighty percent of this project, I will start getting you into user calls as well.
19:05 Samyak Sahu: Uh so we have like some interviews, some sessions with our users. Who are using the product and have a lot of feedback.
19:14 Samyak Sahu: So, that will actually get you a sense of what they are asking for and what kind of systems do we need to build.
19:20 Samyak Sahu: So, our goal is to simply translate the requirements that we're getting from the users to. Like solutions, like you should have a solution in mind.
19:29 Samyak Sahu: Okay, if this is what the exit is asking, this is how I'm supposed to solve it.
19:35 siddhu s: So, okay, that
19:37 Samyak Sahu: is a complete
19:42 siddhu s: Okay. I'll yeah, I'll ti I'll start working, you know, I'll start thinking about which approach should I take and you know, how should I how the agent should be built or something like that.
19:52 siddhu s: And yeah, I'll just have you a video. I'll yeah, show you the loom by the end of the day.
19:58 Samyak Sahu: Okay, okay. Uh, you also, how is that? Like, have you gotten your laptop back, or uh,
20:04 siddhu s: yeah, I got
20:05 Samyak Sahu: my
20:05 siddhu s: laptop back, I got it. I think yeah, Tuesday, I got it back.
20:11 Samyak Sahu: Okay, oh, yeah, do check out Omachi, though. I think. like since you've gotten your like laptop back it's fresh, if you are okay, like uh like migrate all your files, whatever, like and get it backed up.
20:23 Samyak Sahu: But uh highly recommend that you use that because uh it brings new life to old laptops. Like it's yeah performance.
20:30 Samyak Sahu: It's
20:30 siddhu s: there, you know. I have to, I think, I generally have to think about it because, you know, five, six months down the line, if I want to buy a new laptop or something, I'll just exchange my current one.
20:39 siddhu s: And once I go to March or something, it's just, you know, people won't buy if a laptop. People won't buy a Linux laptop or the exchange, the resale value goes down.
20:51 siddhu s: So, yeah, I'll think about it and I'll probably. I mean, it's currently running smoothly since after the RAM expansion, but I'll just.
21:02 Samyak Sahu: Set up Linux, right? You've and you've you get to know that your laptop isn't that old after all. Like, if your machine is like five years old, it's not really old per se.
21:12 Samyak Sahu: Like, even if it's like 8 GB RAM, it's not, it's not that you cannot do anything on it. So, I think the blue.
21:18 Samyak Sahu: that comes with especially Windows laptops, uh, that like limits your understanding. You feel like you need to upgrade everything else, but that is not true.
21:26 Samyak Sahu: Uh, and like you can make a lot of optimizations in your current hardware and make it work uh for a lot of things.
21:34 Samyak Sahu: The way I'm seeing this is also that a lot of uh these uh people would be I think switching over to Linux fleets and Linux systems because uh uh Apple is getting expensive, um, especially for larger businesses and Windows is becoming worse.
21:54 Samyak Sahu: So uh like I think in the next one or two years we'll see like a explosion of Linux laptops in the market.
22:02 Samyak Sahu: Um but yeah, till then uh it's it's like a good performance system. Uh That's what happens.
22:08 siddhu s: Yeah.
22:11 Samyak Sahu: But okay. Okay. Okay, when you're ready, and yeah, just send me that little room to start with by tonight. Even if it's like after an hour or so of research.
22:23 Samyak Sahu: Attention.
22:25 siddhu s: Okay.
22:26 Samyak Sahu: Yeah.
22:27 siddhu s: So just one thing, you know, I want to throw the agent we are building. So I wanted to ask, let's just say the one single agent we are building, it should be, you know, it should be like an Assistant or you know, killers basically a follow-up or it should it should be basically a guide to the video.
22:44 siddhu s: So how should the how should the agent know which video is it? Like that's that's basically you know, okay, should share it the link
22:52 Samyak Sahu: or No, no, the video should not be the input. So, that's the thing, we are not making a generic video to plan converter or that sort.
22:59 Samyak Sahu: No, it's an agent specifically meant to serve as an extension to that video. So, think of it this way: that this video is all it knows.
23:15 Samyak Sahu: This video is how it knows how to improve someone's communication skills. That's it. It will ask you for the exact things that are required of that video.
23:23 Samyak Sahu: The user will not give you give the link to that video to it. You would be programming, you would be hard-coding the videos, instructions onto that agent.
23:34 Samyak Sahu: Okay, so
23:34 siddhu s: for
23:35 Samyak Sahu: right now,
23:36 siddhu s: I should use this video which you have shared: the ultimate 30-day plan to master your communication.
23:42 Samyak Sahu: Yeah, you just go through. Video yourself, understand it thoroughly and see how you can program this behavior into the agent.
23:49 Samyak Sahu: So, let's say the seven-day mark it says the user to do something, at the 40-day market says you to do something.
23:56 Samyak Sahu: Between then, the agent. Agent is giving you some exercises to do. So basically, the tips that are shared on that video need to be actionable advice that the agent sends as a real coach.
24:13 siddhu s: Okay, yeah, I see. So that's the only.
24:15 Samyak Sahu: Video that it knows about if you talk about anything else, it should like this is not expected behavior, but yeah, ideally, it should be like, okay, I don't know what you're talking about,
24:24 siddhu s: let's get
24:24 Samyak Sahu: back training. Okay, that's what,
24:28 siddhu s: yeah, I don't know, okay, okay. So, yeah, that's it, I guess. If I'll set up, I'll make, I'll go through the video, I'll just think about how to, what kind of approach it can use.
24:44 siddhu s: I think
24:44 Samyak Sahu: that's the
24:44 siddhu s: first thing that you
24:45 Samyak Sahu: need to do. Like, today, go through the video. Detail, understand about your understanding, how do you plan that out, and then you can look into how we can map this to an angel.
24:57 siddhu s: Yeah, okay, sure. Thank you.
25:02 Samyak Sahu: Yeah, bye-bye.
25:03 siddhu s: Thank you.






Uh, I think, yeah, I might be audible now. So, yeah, I've written some, you know, notes. I was going through the video and I even went through, yeah, Gemini Notebook, uh, analysed the book.
00:16

And, uh, yeah, so I have, uh, some notes prepared which I'll be using for it. And, you know, sorry for the camera view.
00:29

My camera is a little bit, uh, a bit bad. So, yeah. Let's just start. So, from what I've analysed or, you know, what I've even thought about, I think, uh, one of the first factor, uh, or the first factor or the first principle which I think the HCI agent should be based on, the agent should be, you know
00:50

, it should be more of, it should be love, it should be loving, I think, uh, I would say, you know, it shouldn't be judgmental or, you know, it shouldn't be strict or, uh, it shouldn't be, you know, like, uh, you know, it shouldn't be, I don't know.
01:04

It should help you, the main agent, or for me, the first or the biggest aim of the agent is to let the user succeed, let the user succeed at no, at no matter what the cost is.
01:17

It should not be, you know, it should not be like a teacher or something like that saying, okay, you didn't do this, you failed.
01:23

No, it should be, for me, the analogy of the agent should be more like, okay. Okay, you didn't do this, let's analyze why weren't you able to do this.
01:34

Okay, if that was hard for you, okay, let's start with something smaller or something like that. So, yeah, this was my four main principles which I'm going to be using.
01:44

So, are we basing the agent So yeah, before we start, you know, like before, once the user goes to, goes to the agent, of course the reason he wants to go to a communication improvement agent is, in a way, say that, you know, say that he feels like, you know, he lacks something, or he feels like he might
02:03

get better. So, at the start, ah, the agent might converse with him for a short time, you know, get to know about him a bit, ask about personal details, if you know, he's fine sharing about it, or, you know, sharing about it, and, you know, him, you know, take users opinion, users' opinion, saying what
02:22

is the issue, what is he lagging on. Or, what does he want to improve, or, let's just say, some user feel, you know, someone say, might say, I don't feel like I'm really calm, I want to get calm, or someone say, I don't feel that enthusiasm in my voice, I want to get enthusiastic.
02:40

So, yeah. This, this aren't more about it, this is more, all about the, uh, what I'm trying to say is, yeah, this is all about the feedback, or, you know, what the user wants to achieve, before that.
02:54

Now, you have to see what he wants to achieve, uh, say, the reason why he joined the, or why he, you know, came up to sign that agent.
03:05

So, yeah, once he, yeah, like, we'll follow the presentation. The procedure what's mentioned in the video, once he joined, that, once he joins the agent, the, you, he will record, you know, five minutes, say, or, or even a twenty minutes video, and the question which, which the agent is going to ask
03:24

is going to be tailored, and it's going to be according to, it's going to be according to the fact that it's going to be according to the information it collected from him previously, and it's going to be in a, the questions are going to to be in such a way that it's going to be spontaneous, or legit
03:40

, it's going to, questions are going to be, questions are going to make the user spontaneous, you know, it's going to bring out the spontaneity of the questions, will be in such a manner, you know, it won't let the user, it will make the user guard down.
03:51

It will make the guard down of the user, and, uh, yeah, it will, you know, it won't let the user think, or something like that, it will just bring out his real self.
04:05

And, yeah, and I believe, you know, the questions are, should be in such a manner, which should let the user think how to communicate, yeah, I, yeah, so, I do believe if that happens, in that way, if the results, in the end, in the end, main thing motive is that the, for the 5-minute video, the 5-minute
04:23

video should be spontaneous, of a manner, it should show the real self of him. And, okay, now let's get to the notes about what I've prepared for a while.
04:33

And, you know, I believe agent should be a coach, a good coach, not even a coach, it should be, it should be more of a friend, but yeah, here we can divide the agents into 5 parts, like a coach, Thank you.
04:48

A coach, you know, so that, uh, it will guide the user step by step by step, it doesn't dump, you know, whole of the information on him, say, okay, once the video is done, okay, we are gonna do, I know one is the, Once the video is done, once the user is done analyzing, it's not gonna say, okay, this
05:06

is the plan, A to Z, and we are gonna do it. No, no, it should say, okay, let's start, what do you wanna do, what do you wanna understand, what do you think, what should we change, okay, let's start.
05:17

Let's start with this, okay, what do you wanna change to, and the second part is, uhm, observer, like I've said, the agent's main, agent should more, be, more of a mirror to the user, you know, looking at their conversations with the agent, understanding with the agent, users should an-a-real-an-a, you
05:38

know, realize the shortcomings, or you know realize what does he wanna be or how should he change himself instead of the agent telling you what he should do, should do this, you should do that.
05:49

Instead of that, it should tell the user, it should let the user feel, you know, it should let the user feel that, okay, I find, I think this might be the issues with him.
05:58

I want to work in this part first, this part second, this part third, and yeah, and of course the third part is where the, you know, the train agent, which main part of the agent is to train the user to become developed.
06:12

So in that way, you know, it should, like I said, it shouldn't just give out instructions. It could say, okay, now you feel, if you feel this is the problem, let's just say, if you feel you have a low voice, so how about, you know, we create, um, we create some X's and you know, we create some instances
06:30

where you can use these exercises on day-to-day basis. Let's just, ah, yeah, we could use them day-to-day basis and then in that exercise, you know, we could incorporate those exercises into your daily habits.
06:42

So that, ah, you won't feel, it won't feel a bit unnatural to you and also, you know, in a fact that it might be better.
06:50

It might make you feel better. And after that, ah, yeah. The next thing is more of an inside bit of an inbuilt feature of an agent thing where, you know, the agent should remember everything.
07:05

Like, that's what I've said, it should have the accountability, it should be accountable. Like, it should remember, you know, uh, where the user struggled or, you know, where, which part did he struggle, which part the agent, for an improvement, you know, like, just say, for me, I say, let's just say
07:22

a lot, or something, something like that, uh, I'll see time. So, in that scenario, even the user says, uhm, the agent, I mean, the user says, I want to work on this fact, in, so, as soon as I improve the, let's just say part, and, yeah, so, sometimes, you know, when I'm speaking, I take a, I extend my
07:42

word a bit long, just to think about it, this is also, so, that, these are some of the two shortcomings which I've noticed, so, in, in, in instance, if I am working on both of these things, you know, first I'm working on the, let's just say, part and, then I'm working on the and part, uhm, then I'm working
08:03

on the and part, the agent should remember, how long will it take me to overcome the part, or, you know, improve the part, improve the and part, which, and part, let's just say part.
08:15

So, yeah, that's, that also should, uh, remember, and, uh, with the part of the accountability. But agent should also have a detailed journal, you know, like it should say, okay, user came in at this time, we gave him these exercises, he performed these exercises, these are the exercises he didn't perform
08:34

, why didn't he do it? Then, you know, that why didn't he perform will get to the next part, where the adaptability of the agent comes in.
08:45

And one of the main thing is, you know, that we should build the agent in such a way like where the each the agent should notice how long are we pausing between the words, you know, how many times you are using, uhm, uhm, uhm, uhm, uhm, this and all.
09:03

How many times are we repeating a sentence, how many times a thought process gets stuck, and this all, all of this should be, you know, detailed, a journal detailed, in a detailed way.
09:18

And, yeah, now, again, to adaptability, uhm, yeah, so let's just say, if an, a, if a user is missing out, you know, a couple of classes, or a couple of days, not classes, my bad, a couple of days or something like that.
09:31

So, in that case, in that scenario, uh, it should let the, you should follow up regularly with the user, key, is everything fine, why are you missing, and if he's not missing, and if he's not, and attend, if he missed a couple of sessions.
09:44

So, yeah, you could, you could just ask him, key, do you wanna change something, or do you wanna proceed with a smaller task, or something like that, so just to, you know, make him more comfortable, like, I've said the main principle, the first principle, which it should be based on, should be that the
10:03

aim of the agent is to always make the user succeed, at no matter cost, you know, we could change everything, change the plan, everything should be adaptable, everything should be adaptable in such a way that, that the outcome should always let the user succeed.
10:19

Outcome should always let the user improve, outcome should always let the user develop. Because that is the reason why he came, approached this, you know, why he started, why he is using this agent, so that he can become, It should not, it should never have strict boundaries or strict details or, you
10:34

know, strict rules and procedures. It should be always malleable in such a way that the user should always succeed. And, yeah, regarding that also, yeah, uh, these are just mini points or, you know, something which I've already spoken about getting to that, uh, agent, like I said, you know, even you
10:52

join, when you first join a company, you know, you don't start getting, you don't just go work under the managerial manager or you just don't, you know, start working, you get assigned a buddy, you know, someone of your age or someone, just a couple of your seniors, you know, who's gonna make you feel
11:06

comfortable, who's gonna let down your guard, who's gonna understand, you know, who's gonna make you understand. And, uh, make you realize what are your shortcomings, what are your lags, what do you want to do, how can you improve, and I believe agents should have that personality.
11:22

This is also I should have mentioned, and another thing what I mentioned, like I've said, it should never give out the full plan, it should be step-by-step.
11:31

And, uhm, yeah, like, and this is also regarding the observation, like agents should be, like I've said about the management.
11:40

But the agent should be more of an observer, not a corrective state, like, you know. Let's just say I'm telling my agent, that, uhm, once I upload the video, and, uhm, say that, uhm, you know, I'm ready.
11:54

And I watch it the next day and say, okay, I'm using, uhm, a lot, uh, let's just say I'm speaking on and, uh, okay, so it should just, I should ask me, okay, it's nice, it's a good observation, you've seen me use an and a lot.
12:08

Why do you think that? And, and, yeah, the conversation should be back and forth, you know, make me engage, make me understand why I did that, you know, cause to fix every problem or to fix every issue, the root cause, the main thing is to let us understand what is the root cause.
12:28

And, yeah, that might lead to fixing that. And, another thing, like I have said, this is also part, this is, it should be interesting.
12:36

It should you know, it should not do, decision making should be independent, it should be totally dependent on the user, and it should be independent of the agent.
12:44

Like, user should always say, you know, users, users should always say, that, okay, I have analysed everything. I have analysed all the issues I am facing, I want to fix this issue, I want to fix that issue.
12:56

I mean, yeah, sure, if the user asks the agent for guidance or, you know, suggestions, it might suggest. But it should never, you know, suggest from up front.
13:09

The user should always say, I think these are the issues I am facing, and I think these are the issues I might work in.
13:14

This is how I want to start, and yeah, this is how the agent should be built. It should give the full autonomy of the planning to the user, and it shouldn't, it should never, uh, interfere.
13:27

It should never interfere as long as it feels that the user is failing, then, you know, then also it shouldn't change, it should just give users suggestions, or give users guidance, or not even say guidance, suggestions and other options so that, you know, he might get back on the track.
13:44

And, yeah, this, like we have spoken about, it should be one-to one issue at a time. The agent shouldn't be working on, you know, multiple issues at a time.
13:53

It should be, you know, okay, if the user is going to think about one issue, and he's going to work on that one issue at a time.
14:00

And, uh, regarding that, you I think this is an optional feature. After, you know, every test or everything, not even every test, every task or something like that, it could ask, it could ask the user, okay, let's just, you know, give me a 2-minute video or so that, so just, you know, collect evidence
14:19

and analyze all of the feature, analyze, you know, not the feature, analyze the total video and then, you know, it should ask, and it should ask not just, you know, make an outcome on it, it should ask what the user thinks of himself, what did he think, what are the changes he wants to make, you know
14:39

, after he records the video, let's just say, after a test or after a task or something, he comes back, he records the video, and it should, yeah, it should, in the background, it should, you know, analyze everything, but that shouldn't be the conclusive outcome.
14:52

The conclusive outcome should be determined by, eh, the fact that it should ask, it should determine the fact of, fact that, I think, yeah, it should be determined in a way.
15:05

Sorry. Sorry. Ha. It should be determined what user thinks. You know, ok, what user thinks, how can it be analyzed and how can we approve.
15:16

And, uh, another thing, yeah, this also, like I said, since the agent should be more of a friend than buddy, for this to work and for the user to succeed and everything, trust.
15:27

Trust for me is an important factor. For anyone to succeed, if you are helping anyone, just trust for them should be an important factor.
15:35

And, let's just say, you know, the agent should never assume the user is lying or never learn. Never assume the user is lying.
15:42

Let's just say, after a task or something, the user records a video. In that, it might feel like, you know, users haven't improved a bit.
15:51

But the user's feeling, if he's feeling, he has improved. Then the agent should accept that, in a way. I mean, in a way, that he has improved.
16:01

I mean, yeah, we could detail, it should also give, it should also think about its analysis and it should take the user's output.
16:08

But, I'm, you know, what I'm trying to say is, it should 100% trust the users. Let's just see if a user is giving wrong feedback or wrong analysis of himself.
16:17

It shouldn't be that he's lying or he's dishonest. Yeah, he may be ignorant, but he isn't dishonest. So, this is the last principle.
16:27

So, basically, the, it should be, you know, agent should, for me, building an agent, these are the two main behavior principles, uh, two or three main behavior principles, four main behavior principles.
16:41

The first one should be, the first one, all, its aim of the agent is to always make sure the user succeeds.
16:47

The second one is that, you know, it should never assume the user's dishonest or dishonest or he is lying. And the third one is we are always to focus on one Yeah, fourth one for me is that the user should make the plan himself.
17:13

Or, you know, every decision should be from the user and not from the agent. And, yeah, this is what I've analysed.
17:20

This is what I think of the video, that's all. Thank you.