import './globals.css';

export const metadata = {
  title: 'Callback',
  description: 'AI-powered job application agent.',
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body className="bg-background text-foreground antialiased">
        {children}
      </body>
    </html>
  );
}