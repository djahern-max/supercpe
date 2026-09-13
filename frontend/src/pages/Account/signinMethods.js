// 030: the words for an account's sign-in methods, from the server's
// derived list. Anything without "google" reads as Password.
export function signinMethodsLabel(methods) {
  const hasPassword = methods.includes("password");
  const hasGoogle = methods.includes("google");
  if (hasPassword && hasGoogle) return "Password and Google";
  if (hasGoogle) return "Google";
  return "Password";
}
