<?php
if ($_SERVER["REQUEST_METHOD"] == "POST") {
    $to = "info@qbytz.com";
    $subject = "New Course Registration";
    $name = $_POST["name"];
    $email = $_POST["email"];
    $course = $_POST["course"];

    $message = "Name: $name\nEmail: $email\nSelected Course: $course";
    $headers = "From: noreply@qbytz.com";

    if (mail($to, $subject, $message, $headers)) {
        header("Location: response.html?status=success");
        exit();
    } else {
        header("Location: response.html?status=error");
        exit();
    }
}
?>
