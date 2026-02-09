# School Portal (Flask)

#### VIDEO DEMO URL = <https://youtu.be/cqhJ9qYn2NA>


A role-based school portal built with Flask + SQLite. It supports admin, teacher, and student dashboards with messaging, circulars, homework, and school news.
Description

School Portal is a full-stack web application built with Flask and SQLite that simulates a real-world school communication and management system. The goal of this project was to design a role-based platform that allows administrators, teachers, and students to interact securely within a single portal, each with different permissions and responsibilities.

In many schools, communication is fragmented across messaging apps, notice boards, and paper circulars. This project attempts to solve that problem by centralizing school news, homework, circulars, and direct messaging into one unified system. Each user logs in once and is presented with a dashboard tailored to their role.

User Roles and Functionality

The application supports three distinct user roles:

Admin

Teacher

Student

Each role has access only to the features relevant to them. This is enforced through Flask session management and conditional routing.

Admins have the highest level of control. They can:

Broadcast messages to all teachers and students

Post official school news visible across the platform

Upload circulars and homework for specific grades

View an admin dashboard showing all users and their online status

Monitor unread message counts system-wide

Teachers act as intermediaries between the administration and students. They can:

Receive messages from students and admins

Send messages to individual students or admins

Upload homework and circulars for the classes they handle

View received, sent, and unread messages

Track whether messages have been seen

Students primarily consume information and communicate upward. They can:

View homework and circulars assigned to their grade

Read school news posted by admins

Send messages to teachers

Track unread messages and announcements

Messaging System

One of the core components of this project is the internal messaging system. Messages are stored in the SQLite database with sender, receiver, timestamp, and a “seen” flag. Each inbox shows:

Unread messages

Received messages

Sent messages

Unread counts automatically decrease once a message is opened, closely mimicking real email or messaging platforms.

Technical Design

The backend is written entirely in Python using Flask, with SQLite as the database via the cs50 SQL library. Passwords are securely hashed using Werkzeug. HTML templates are rendered with Jinja, allowing dynamic role-based content.

The project follows a simple but organized structure:

app.py contains all routes, authentication logic, and database queries

templates/ holds Jinja HTML files

static/ contains CSS and uploaded files

Uploaded files are stored safely in static/uploads

Additional features include:

Dark mode toggle for improved usability

A settings page for changing passwords

Online status tracking using last_seen timestamps

A developer reset route for testing purposes

Why This Project

I chose this project because it combines authentication, authorization, database design, file uploads, and UI logic into a single real-world application. It demonstrates my understanding of Flask routing, session handling, SQL queries, and full-stack web development concepts taught throughout CS50x.

This project represents the culmination of what I learned in CS50, applying it to a practical system that mirrors software used in actual schools.


  ## PRECAUTION!!
  - If you want to clear all the data type the link `dev_reset` and all the data even admins will be removed thimk before typing or else all data will be eradicated.
  - If you want to register as a new admin type in the password `the-password234!`. This cam also be customizable by going to apps.py and setting the new password in `app.secret_key` just below the imports.
