-- Database Setup for AI Chatbot Lead Generator
-- Run this SQL script to manually create the database and tables

-- Create database
CREATE DATABASE IF NOT EXISTS chatbot_db;
USE chatbot_db;

-- Create leads table with requested schema
CREATE TABLE IF NOT EXISTS leads (
    userid INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(255) NOT NULL,
    mailid VARCHAR(255),
    phonenumber VARCHAR(100),
    conversation TEXT,
    timestart TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    timeend TIMESTAMP NULL,
    chatbot_id VARCHAR(255),
    company_name VARCHAR(255),
    session_id VARCHAR(255),
    questions_asked INT DEFAULT 0,
    INDEX idx_chatbot_id (chatbot_id),
    INDEX idx_mailid (mailid),
    INDEX idx_session_id (session_id)
);

-- Create chatbots table
CREATE TABLE IF NOT EXISTS chatbots (
    id INT AUTO_INCREMENT PRIMARY KEY,
    chatbot_id VARCHAR(255) UNIQUE NOT NULL,
    company_name VARCHAR(255) NOT NULL,
    website_url TEXT NOT NULL,
    embed_code TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_chatbot_id (chatbot_id)
);

-- Show tables
SHOW TABLES;

-- Describe tables structure
DESCRIBE leads;
DESCRIBE chatbots;
