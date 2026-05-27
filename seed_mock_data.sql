-- Mock Teacher Personas for Demo

INSERT INTO faculty_profiles (
    email, first_name, last_name, discipline, grade_band, years_experience, current_module, tailoring_query
) VALUES 
(
    'novice-math@paceacademy.edu', 
    'Sarah', 
    'Miller', 
    '6th Grade Math', 
    '6-8', 
    2, 
    'Introduction to Fractions', 
    'I struggle with keeping students focused during direct instruction. Looking for active learning tips.'
),
(
    'mid-english@paceacademy.edu', 
    'David', 
    'Thompson', 
    '10th Grade English', 
    '9-12', 
    7, 
    'Shakespearean Tragedy', 
    'Interested in strategies for improving student writing voice and peer review efficacy.'
),
(
    'veteran-history@paceacademy.edu', 
    'Eleanor', 
    'Rigby', 
    'AP US History', 
    '9-12', 
    15, 
    'The Civil Rights Movement', 
    'Searching for ways to incorporate primary source analysis without overwhelming students with reading volume.'
)
ON CONFLICT (email) DO NOTHING;
