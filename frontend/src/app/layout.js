import { Inter } from 'next/font/google';
import Navbar from '@/components/layout/Navbar';
// import './globals.css';
 
const inter = Inter({ subsets: ['latin'] });

export const metadata = {
  title: 'Callback',
  description: 'AI-powered job application agent.',
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body className={inter.className}>
        <Navbar />
        {children}
      </body>
    </html>
  );
}